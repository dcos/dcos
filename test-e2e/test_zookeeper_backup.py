"""
Tests for the ZooKeeper backup/restore scripts.
"""

import logging
import subprocess
import textwrap
import uuid
from pathlib import Path
from typing import List

import pytest
from _pytest.fixtures import SubRequest
from cluster_helpers import wait_for_dcos_oss
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Output
from kazoo.client import KazooClient
from kazoo.exceptions import NoNodeError


LOGGER = logging.getLogger(__name__)

# Arbitrary value written to ZooKeeper.
FLAG = b'flag'


def _zk_set_flag(hosts: str, ephemeral: bool = False) -> str:
    """
    Store the `FLAG` value in ZooKeeper in a random Znode.
    """
    znode = '/{}'.format(uuid.uuid4())
    zk_client = KazooClient(hosts=hosts)
    zk_client.start()
    zk_client.create(znode, makepath=True, ephemeral=ephemeral)
    zk_client.set(znode, FLAG)
    zk_client.stop()
    return znode


def _zk_check_flag(hosts: str, znode: str) -> None:
    """
    The `FLAG` value is found in ZooKeeper at the `znode` path.
    """
    zk_client = KazooClient(hosts=hosts, read_only=True)
    zk_client.start()
    value = zk_client.get(znode)
    zk_client.stop()
    assert value[0] == FLAG


def _bash(cmd: List[str]) -> None:
    """
    Execute `cmd` in a subprocess, log potential errors.
    """
    LOGGER.debug('BASH ARGS: {}'.format(' '.join(cmd)))
    try:
        result = subprocess.check_output(
            args=' '.join(cmd),
            stderr=subprocess.STDOUT,
            shell=True,
        )
        LOGGER.debug(result.decode())
    except subprocess.CalledProcessError as exc:
        LOGGER.error(exc.output.decode())
        raise


BACKUP_SCRIPT = textwrap.dedent(
    """\
#!/bin/bash -e

DESTINATION_DIR=$PWD
REMOTE_TMP_DIR=/tmp/zk_backup

usage() {
  echo "Usage: $0 [-h] [-p ZK_BACKUP_DEST_DIR] [-i SSH_KEY_PATH] [-t REMOTE_TMP_DIR] SSH_USER@MASTER_HOST" 1>&2
}
exit_abnormal() {
  usage
  exit 1
}
while getopts ":hp:t:i:" opt; do
  case $opt in
    h)
      usage
      exit 0
    ;;
    p) DESTINATION_DIR=$OPTARG
    ;;
    t) REMOTE_TMP_DIR=$OPTARG
    ;;
    i) SSH_KEY_PATH=$OPTARG
    ;;
    \\?) echo "Invalid option -$OPTARG" 1>&2
        exit_abnormal
    ;;
    :) echo "Error: -$OPTARG requires an argument." 1>&2
       exit_abnormal
    ;;
    *) exit_abnormal
    ;;
  esac
done

shift $((OPTIND - 1))
if (($# != 1)); then
  exit_abnormal
fi

CONN=$1
KEY=${SSH_KEY_PATH:+"-i $SSH_KEY_PATH"}
OPTS='-o ConnectTimeout=3 -o ConnectionAttempts=1
-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'

ssh $OPTS $KEY -tt $CONN << EOF
  set -e
  sudo mkdir -p $REMOTE_TMP_DIR
  sudo systemctl stop dcos-exhibitor
  sudo cp -pr /var/lib/dcos/exhibitor/zookeeper ${REMOTE_TMP_DIR}/zookeeper
  sudo systemctl start dcos-exhibitor
  sudo tar --exclude 'myid' --exclude 'zookeeper.out' -pcvzf \\
  ${REMOTE_TMP_DIR}/zk_backup-'$(date +%Y-%m-%d_%H-%M-%S)'.tar.gz -C $REMOTE_TMP_DIR ./zookeeper
  sudo rm -rf ${REMOTE_TMP_DIR}/zookeeper
  exit 0
EOF

scp $OPTS $KEY -r ${CONN}:${REMOTE_TMP_DIR}/zk_backup-'*'.tar.gz ${DESTINATION_DIR}/ 2> /dev/null

ssh $OPTS $KEY -tt $CONN << EOF
  set -e
  sudo rm -rf $REMOTE_TMP_DIR
  exit 0
EOF
exit 0
    """
)


RESTORE_SCRIPT = textwrap.dedent(
    """\
#!/bin/bash -e

SSH_USER='root'
REMOTE_TMP_DIR=/tmp/zk_restore

usage() {
  echo "Usage: $0 [-h] [-i SSH_KEY_PATH] [-l SSH_USER] [-t REMOTE_TMP_DIR] ZK_BACKUP_PATH MASTER_HOSTNAME..." 1>&2
}
exit_abnormal() {
  usage
  exit 1
}
while getopts ":ht:i:l:" opt; do
  case $opt in
    h)
      usage
      exit 0
    ;;
    t) REMOTE_TMP_DIR=$OPTARG
    ;;
    i) SSH_KEY_PATH=$OPTARG
    ;;
    l) SSH_USER=$OPTARG
    ;;
    \\?) echo "Invalid option -$OPTARG" 1>&2
        exit_abnormal
    ;;
    :) echo "Error: -$OPTARG requires an argument." 1>&2
       exit_abnormal
    ;;
    *) exit_abnormal
    ;;
  esac
done

shift $((OPTIND - 1))
if (($# < 2)); then
  exit_abnormal
fi

BACKUP_PATH=$1
shift

OPTS='-o ConnectTimeout=3 -o ConnectionAttempts=1
-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'
KEY=${SSH_KEY_PATH:+"-i $SSH_KEY_PATH"}

for i in "$@"
do
ssh $OPTS -tt $KEY ${SSH_USER}@${i} << EOF
  set -e
  sudo systemctl stop dcos-exhibitor
  sudo mkdir -p $REMOTE_TMP_DIR
  exit 0
EOF
scp $OPTS $KEY $BACKUP_PATH $SSH_USER@${i}:${REMOTE_TMP_DIR}/zk_backup.tar.gz 2> /dev/null
done

for i in "$@"
do
ssh $OPTS -tt $KEY ${SSH_USER}@${i} << EOF
  set -e
  sudo rm -rf /var/lib/dcos/exhibitor/zookeeper
  sudo tar -C /var/lib/dcos/exhibitor --same-owner -xzvf ${REMOTE_TMP_DIR}/zk_backup.tar.gz
  sudo systemctl start dcos-exhibitor
  sudo rm -rf $REMOTE_TMP_DIR
  exit 0
EOF
done
exit 0
    """
)


class TestZooKeeperBackup:

    def test_transaction_log_backup_and_restore(
        self,
        artifact_path: Path,
        docker_backend: Docker,
        tmp_path: Path,
        request: SubRequest,
        log_dir: Path,
    ) -> None:
        """
        In a 3-master cluster, backing up the transaction log of ZooKeeper on
        one node and restoring from the backup on all master results in a
        functioning DC/OS cluster with previously backed up Znodes restored.
        """
        with Cluster(
            cluster_backend=docker_backend,
            masters=3,
            agents=0,
            public_agents=0,
        ) as cluster:
            cluster.install_dcos_from_path(
                dcos_installer=artifact_path,
                dcos_config=cluster.base_config,
                ip_detect_path=docker_backend.ip_detect_path,
            )
            wait_for_dcos_oss(
                cluster=cluster,
                request=request,
                log_dir=log_dir,
            )
            masters = cluster.masters

            # Write to ZooKeeper before backup
            zk_hostports = ','.join([str(m.public_ip_address) + ':2181' for m in masters])
            persistent_flag = _zk_set_flag(zk_hostports)
            ephemeral_flag = _zk_set_flag(zk_hostports, ephemeral=True)

            # Backup ZooKeeper state from single master node
            script_path = tmp_path / 'dcos-zk-backup'
            script_path.write_text(BACKUP_SCRIPT)
            script_path.chmod(0o755)
            master = next(iter(masters))
            _bash(cmd=[
                str(script_path),
                '-i', str(master._ssh_key_path),
                '-p', str(tmp_path),
                'root@{}'.format(master.public_ip_address),
            ])

            # Store a datapoint which we expect to be lost.
            not_backed_up_flag = _zk_set_flag(zk_hostports)

            # Restore ZooKeeper state from backup to all master nodes
            script_path = tmp_path / 'dcos-zk-restore'
            result = subprocess.check_output(
                args='ls {} | grep zk_backup'.format(tmp_path),
                shell=True,
            )
            backup_filename = result.decode().strip('\n')
            script_path.write_text(RESTORE_SCRIPT)
            script_path.chmod(0o755)
            master_ips = [str(m.public_ip_address) for m in masters]
            _bash(cmd=[
                str(script_path),
                '-i', str(master._ssh_key_path),
                '-l', 'root',
                str(tmp_path / backup_filename),
            ] + master_ips)

            # Assert DC/OS is intact.
            wait_for_dcos_oss(
                cluster=cluster,
                request=request,
                log_dir=log_dir,
            )

            # Read from ZooKeeper after restore
            _zk_check_flag(zk_hostports, persistent_flag)
            with pytest.raises(NoNodeError):
                _zk_check_flag(zk_hostports, ephemeral_flag)
            with pytest.raises(NoNodeError):
                _zk_check_flag(zk_hostports, not_backed_up_flag)

    def test_snapshot_backup_and_restore(
        self,
        artifact_path: Path,
        docker_backend: Docker,
        tmp_path: Path,
        request: SubRequest,
        log_dir: Path,
    ) -> None:
        """
        In a 3-master cluster, backing up a snapshot of ZooKeeper on
        one node and restoring from the backup on all master results in a
        functioning DC/OS cluster with previously backed up Znodes restored.
        """
        with Cluster(
            cluster_backend=docker_backend,
            masters=3,
            agents=0,
            public_agents=0,
        ) as cluster:
            cluster.install_dcos_from_path(
                dcos_installer=artifact_path,
                dcos_config=cluster.base_config,
                ip_detect_path=docker_backend.ip_detect_path,
            )
            wait_for_dcos_oss(
                cluster=cluster,
                request=request,
                log_dir=log_dir,
            )
            masters = cluster.masters

            for master in masters:
                # Modify Exhibitor conf, generating ZooKeeper conf (set `snapCount=1`)
                master.run(
                    args=[
                        'sed',
                        '-i', "'s/zoo-cfg-extra=/zoo-cfg-extra=snapCount\\\\=1\\&/'",
                        '/opt/mesosphere/active/exhibitor/usr/exhibitor/start_exhibitor.py',
                    ],
                    shell=True,
                    output=Output.LOG_AND_CAPTURE,
                )
            for master in masters:
                # Restart Exhibitor
                master.run(['sudo', 'systemctl', 'restart', 'dcos-exhibitor'])

            wait_for_dcos_oss(
                cluster=cluster,
                request=request,
                log_dir=log_dir,
            )

            # Write to ZooKeeper multiple times before backup
            zk_hostports = ','.join([str(m.public_ip_address) + ':2181' for m in masters])
            persistent_flag = _zk_set_flag(zk_hostports)
            ephemeral_flag = _zk_set_flag(zk_hostports, ephemeral=True)

            # Extra ZooKeeper write, triggering snapshot creation due to
            # `snapCount=1`. After this we can be sure the previous writes are
            # contained in at least one of the generated snapshots.
            _zk_set_flag(zk_hostports)

            # Backup ZooKeeper state from single master node
            script_path = tmp_path / 'dcos-zk-backup'
            script_path.write_text(BACKUP_SCRIPT)
            script_path.chmod(0o755)
            master = next(iter(masters))
            _bash(cmd=[
                str(script_path),
                '-i', str(master._ssh_key_path),
                '-p', str(tmp_path),
                'root@{}'.format(master.public_ip_address),
            ])

            # Store a datapoint which we expect to be lost.
            not_backed_up_flag = _zk_set_flag(zk_hostports)

            # Restore ZooKeeper state from backup to all master nodes
            script_path = tmp_path / 'dcos-zk-restore'
            result = subprocess.check_output(
                args='ls {} | grep zk_backup'.format(tmp_path),
                shell=True,
            )
            backup_filename = result.decode().strip('\n')
            script_path.write_text(RESTORE_SCRIPT)
            script_path.chmod(0o755)
            master_ips = [str(m.public_ip_address) for m in masters]
            _bash(cmd=[
                str(script_path),
                '-i', str(master._ssh_key_path),
                '-l', 'root',
                str(tmp_path / backup_filename),
            ] + master_ips)

            # Assert DC/OS is intact.
            wait_for_dcos_oss(
                cluster=cluster,
                request=request,
                log_dir=log_dir,
            )

            # Read from ZooKeeper after restore
            _zk_check_flag(zk_hostports, persistent_flag)
            with pytest.raises(NoNodeError):
                _zk_check_flag(zk_hostports, ephemeral_flag)
            with pytest.raises(NoNodeError):
                _zk_check_flag(zk_hostports, not_backed_up_flag)

