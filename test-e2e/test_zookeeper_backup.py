"""
Tests for the ZooKeeper backup/restore scripts.
"""

import logging
import shlex
import subprocess
import uuid
from pathlib import Path
from typing import List

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
    try:
        zk_client.create(znode, makepath=True, ephemeral=ephemeral)
        zk_client.set(znode, FLAG)
    finally:
        zk_client.stop()
    return znode


def _zk_flag_exists(hosts: str, znode: str) -> bool:
    """
    The `FLAG` value exists in ZooKeeper at the `znode` path.
    """
    zk_client = KazooClient(hosts=hosts, read_only=True)
    zk_client.start()
    try:
        value = zk_client.get(znode)
    except NoNodeError:
        return False
    finally:
        zk_client.stop()
    return bool(value[0] == FLAG)


def _bash(cmd: List[str]) -> None:
    """
    Execute `cmd` in a subprocess, log potential errors.
    """
    LOGGER.debug('BASH ARGS: {}'.format(' '.join(cmd)))
    try:
        result = subprocess.check_output(
            args=' '.join(shlex.quote(arg) for arg in cmd),
            stderr=subprocess.STDOUT,
            shell=True,
        )
        LOGGER.debug(result.decode())
    except subprocess.CalledProcessError as exc:
        LOGGER.error(exc.output.decode())
        raise


class TestZooKeeperBackup:
    """
    Within the context of DC/OS ZooKeeper can be backed up on a running
    cluster and a previous state can be restored with minimal downtime.

    NOTE: Tests in this class require the following commands to be available
        in the environment: `bash`, `ssh` and `scp`

    """

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
        fixture_root = Path('fixtures').absolute()
        fixture_dir = fixture_root / 'zk_scripts'

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
            ssh_key_path = next(iter(cluster.masters))._ssh_key_path
            master_ips = [str(m.public_ip_address) for m in cluster.masters]
            zk_hostports = ','.join([m + ':2181' for m in master_ips])

            # Write to ZooKeeper before backup
            persistent_flag = _zk_set_flag(zk_hostports)
            ephemeral_flag = _zk_set_flag(zk_hostports, ephemeral=True)

            # Generate and download ZooKeeper backup
            _bash(cmd=[
                str(fixture_dir / 'dcos-zk-backup.sh'),
                '-l', 'root',
                '-i', str(ssh_key_path),
                str(tmp_path),
                next(iter(master_ips)),
            ])

            # Store a datapoint which we expect to be lost.
            not_backed_up_flag = _zk_set_flag(zk_hostports)

            # Find ZooKeeper backup filename
            result = subprocess.check_output(
                args='ls {} | grep zk_backup'.format(shlex.quote(str(tmp_path))),
                shell=True,
            )
            backup_filename = result.decode().strip('\n')

            # Restore ZooKeeper state from backup to all master nodes
            _bash(cmd=[
                str(fixture_dir / 'dcos-zk-restore.sh'),
                '-l', 'root',
                '-i', str(ssh_key_path),
                str(tmp_path / backup_filename),
            ] + master_ips)

            # Assert DC/OS is intact.
            wait_for_dcos_oss(
                cluster=cluster,
                request=request,
                log_dir=log_dir,
            )

            # Read from ZooKeeper after restore
            assert _zk_flag_exists(zk_hostports, persistent_flag)
            assert not _zk_flag_exists(zk_hostports, ephemeral_flag)
            assert not _zk_flag_exists(zk_hostports, not_backed_up_flag)

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
        fixture_root = Path('fixtures').absolute()
        fixture_dir = fixture_root / 'zk_scripts'

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

            # Modify Exhibitor conf, generating ZooKeeper conf (set `snapCount=1`).
            # This config change instructs ZooKeeper to generate a new snapshot for
            # every single transaction.
            for master in masters:
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

            # Begin the backup/restore test procedure
            ssh_key_path = next(iter(masters))._ssh_key_path
            master_ips = [str(m.public_ip_address) for m in masters]
            zk_hostports = ','.join([m + ':2181' for m in master_ips])

            # Write to ZooKeeper multiple times before backup
            persistent_flag = _zk_set_flag(zk_hostports)
            ephemeral_flag = _zk_set_flag(zk_hostports, ephemeral=True)

            # Extra ZooKeeper write, triggering snapshot creation due to
            # `snapCount=1`. After this we can be sure the previous writes are
            # contained in at least one of the generated snapshots.
            _zk_set_flag(zk_hostports)

            # Backup ZooKeeper state from single master node
            _bash(cmd=[
                str(fixture_dir / 'dcos-zk-backup.sh'),
                '-l', 'root',
                '-i', str(ssh_key_path),
                str(tmp_path),
                next(iter(master_ips)),
            ])

            # Store a datapoint which we expect to be lost.
            not_backed_up_flag = _zk_set_flag(zk_hostports)

            # Find generated ZooKeeper backup file name
            result = subprocess.check_output(
                args='ls {} | grep zk_backup'.format(shlex.quote(str(tmp_path))),
                shell=True,
            )
            backup_filename = result.decode().strip('\n')

            # Restore ZooKeeper state from backup to all master nodes
            _bash(cmd=[
                str(fixture_dir / 'dcos-zk-restore.sh'),
                '-l', 'root',
                '-i', str(ssh_key_path),
                str(tmp_path / backup_filename),
            ] + master_ips)

            # Assert DC/OS is intact.
            wait_for_dcos_oss(
                cluster=cluster,
                request=request,
                log_dir=log_dir,
            )

            # Read from ZooKeeper after restore
            assert _zk_flag_exists(zk_hostports, persistent_flag)
            assert not _zk_flag_exists(zk_hostports, ephemeral_flag)
            assert not _zk_flag_exists(zk_hostports, not_backed_up_flag)
