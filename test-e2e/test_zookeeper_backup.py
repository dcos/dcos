"""
Tests for the ZooKeeper backup/restore via `dcos-zk`.
"""

import logging
import uuid
from pathlib import Path
from typing import Set

import pytest
from _pytest.fixtures import SubRequest

from cluster_helpers import wait_for_dcos_oss
from conditional import E2E_SAFE_DEFAULT, escape, only_changed, trailing_path
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Node, Output
from kazoo.client import KazooClient
from kazoo.exceptions import NoNodeError
from kazoo.retry import KazooRetry


LOGGER = logging.getLogger(__name__)

# Arbitrary value written to ZooKeeper.
FLAG = b'flag'


@pytest.fixture
def zk_client(static_three_master_cluster: Cluster) -> KazooClient:
    """
    ZooKeeper client connected to a given DC/OS cluster.
    """
    zk_hostports = ','.join(['{}:2181'.format(m.public_ip_address)
                             for m in static_three_master_cluster.masters])
    retry_policy = KazooRetry(
        max_tries=-1,
        delay=1,
        backoff=1,
        max_delay=600,
        ignore_expire=True,
    )
    zk_client = KazooClient(
        hosts=zk_hostports,
        # Avoid failure due to client session timeout.
        timeout=40,
        # Work around https://github.com/python-zk/kazoo/issues/374
        connection_retry=retry_policy,
        command_retry=retry_policy,
    )
    zk_client.start()
    try:
        yield zk_client
    finally:
        zk_client.stop()
        zk_client.close()


def _zk_set_flag(zk: KazooClient, ephemeral: bool = False) -> str:
    """
    Store the `FLAG` value in ZooKeeper in a random Znode.
    """
    znode = '/{}'.format(uuid.uuid4())
    zk.retry(zk.create, znode, makepath=True, ephemeral=ephemeral)
    zk.retry(zk.set, znode, FLAG)
    return znode


def _zk_flag_exists(zk: KazooClient, znode: str) -> bool:
    """
    The `FLAG` value exists in ZooKeeper at `znode` path.
    """
    try:
        value = zk.retry(zk.get, znode)
    except NoNodeError:
        return False
    return bool(value[0] == FLAG)


@pytest.mark.skipif(
    only_changed(E2E_SAFE_DEFAULT + [
        # All packages safe except named packages
        'packages/*/**',
        '!packages/{exhibitor,java}/**',
        # All e2e tests safe except this test
        'test-e2e/test_*', '!' + escape(trailing_path(__file__, 2)),
    ]),
    reason='Only safe files modified',
)
class TestZooKeeperBackup:
    """
    Within the context of DC/OS ZooKeeper can be backed up on a running
    cluster and a previous state can be restored.
    """

    def test_transaction_log_backup_and_restore(
        self,
        static_three_master_cluster: Cluster,
        zk_client: KazooClient,
        tmp_path: Path,
        request: SubRequest,
        log_dir: Path,
    ) -> None:
        """
        In a 3-master cluster, backing up the transaction log of ZooKeeper on
        one node and restoring from the backup on all master results in a
        functioning DC/OS cluster with previously backed up Znodes restored.
        """
        # Write to ZooKeeper before backup
        persistent_flag = _zk_set_flag(zk_client)
        ephemeral_flag = _zk_set_flag(zk_client, ephemeral=True)

        random = uuid.uuid4().hex
        backup_name = 'zk-backup-{random}.tar.gz'.format(random=random)
        backup_local_path = tmp_path / backup_name

        # Take ZooKeeper backup from one master node.
        _do_backup(next(iter(static_three_master_cluster.masters)), backup_local_path)

        # Store a datapoint which we expect to get lost.
        not_backed_up_flag = _zk_set_flag(zk_client)

        # Restore ZooKeeper from backup on all master nodes.
        _do_restore(static_three_master_cluster.masters, backup_local_path)

        # Read from ZooKeeper after restore
        assert _zk_flag_exists(zk_client, persistent_flag)
        assert _zk_flag_exists(zk_client, ephemeral_flag)
        assert not _zk_flag_exists(zk_client, not_backed_up_flag)

        # Assert that DC/OS is intact.
        wait_for_dcos_oss(
            cluster=static_three_master_cluster,
            request=request,
            log_dir=log_dir,
        )

    def test_snapshot_backup_and_restore(
        self,
        static_three_master_cluster: Cluster,
        zk_client: KazooClient,
        tmp_path: Path,
        request: SubRequest,
        log_dir: Path,
    ) -> None:
        """
        In a 3-master cluster, backing up a snapshot of ZooKeeper on
        one node and restoring from the backup on all master results in a
        functioning DC/OS cluster with previously backed up Znodes restored.
        """
        # Modify Exhibitor conf, generating ZooKeeper conf (set
        # `snapCount=1`). This config change instructs ZooKeeper to Adding
        # the `snapCount` here only works as long as DC/OS does not set it.
        args = [
            'sed',
            '-i', "'s/zoo-cfg-extra=/zoo-cfg-extra=snapCount\\\\=1\\&/'",
            '/opt/mesosphere/active/exhibitor/usr/exhibitor/start_exhibitor.py',
        ]
        for master in static_three_master_cluster.masters:
            master.run(
                args=args,
                shell=True,
                output=Output.LOG_AND_CAPTURE,
            )
        for master in static_three_master_cluster.masters:
            master.run(['systemctl', 'restart', 'dcos-exhibitor'])

        wait_for_dcos_oss(
            cluster=static_three_master_cluster,
            request=request,
            log_dir=log_dir,
        )

        # Write to ZooKeeper multiple times before backup
        persistent_flag = _zk_set_flag(zk_client)
        ephemeral_flag = _zk_set_flag(zk_client, ephemeral=True)

        # Extra ZooKeeper write, triggering snapshot creation due to
        # `snapCount=1`. After this we can be sure the previous writes are
        # contained in at least one of the generated snapshots.
        _zk_set_flag(zk_client)

        random = uuid.uuid4().hex
        backup_name = 'zk-backup-{random}.tar.gz'.format(random=random)
        backup_local_path = tmp_path / backup_name

        # Take ZooKeeper backup from one master node.
        _do_backup(next(iter(static_three_master_cluster.masters)), backup_local_path)

        # Store a datapoint which we expect to be lost.
        not_backed_up_flag = _zk_set_flag(zk_client)

        # Restore ZooKeeper from backup on all master nodes.
        _do_restore(static_three_master_cluster.masters, backup_local_path)

        # Read from ZooKeeper after restore
        assert _zk_flag_exists(zk_client, persistent_flag)
        assert _zk_flag_exists(zk_client, ephemeral_flag)
        assert not _zk_flag_exists(zk_client, not_backed_up_flag)

        # Assert DC/OS is intact.
        wait_for_dcos_oss(
            cluster=static_three_master_cluster,
            request=request,
            log_dir=log_dir,
        )


def _do_backup(master: Node, backup_local_path: Path) -> None:
    """
    Automated ZooKeeper backup procedure.
    Intended to be consistent with the documentation.
    https://jira.mesosphere.com/browse/DCOS-51647
    """
    master.run(args=['systemctl', 'stop', 'dcos-exhibitor'])

    backup_name = backup_local_path.name
    # This must be an existing directory on the remote server.
    backup_remote_path = Path('/etc/') / backup_name
    master.run(
        args=[
            '/opt/mesosphere/bin/dcos-shell',
            'dcos-zk',
            'backup',
            str(backup_remote_path),
            '-v',
        ],
        output=Output.LOG_AND_CAPTURE,
    )

    master.run(args=['systemctl', 'start', 'dcos-exhibitor'])

    master.download_file(
        remote_path=backup_remote_path,
        local_path=backup_local_path,
    )

    master.run(args=['rm', str(backup_remote_path)])


def _do_restore(all_masters: Set[Node], backup_local_path: Path) -> None:
    """
    Automated ZooKeeper restore from backup procedure.
    Intended to be consistent with the documentation.
    https://jira.mesosphere.com/browse/DCOS-51647
    """
    backup_name = backup_local_path.name
    backup_remote_path = Path('/etc/') / backup_name

    for master in all_masters:
        master.send_file(
            local_path=backup_local_path,
            remote_path=backup_remote_path,
        )

    for master in all_masters:
        master.run(args=['systemctl', 'stop', 'dcos-exhibitor'])

    for master in all_masters:
        master.run(
            args=[
                '/opt/mesosphere/bin/dcos-shell',
                'dcos-zk', 'restore', str(backup_remote_path), '-v',
            ],
            output=Output.LOG_AND_CAPTURE,
        )

    for master in all_masters:
        master.run(args=['systemctl', 'start', 'dcos-exhibitor'])
