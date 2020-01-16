"""
Tests for the Etcd backup/restore via `dcos-etcdctl`.
"""

import logging
import subprocess
import uuid
from pathlib import Path
from typing import Set

import pytest
from _pytest.fixtures import SubRequest

from cluster_helpers import wait_for_dcos_oss
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Node, Output


LOGGER = logging.getLogger(__name__)


@pytest.fixture
def three_master_cluster(
    artifact_path: Path,
    docker_backend: Docker,
    request: SubRequest,
    log_dir: Path,
) -> Cluster:
    """Spin up a highly-available DC/OS cluster with three master nodes."""
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
        yield cluster


def _do_backup(master: Node, backup_local_path: Path) -> None:

    backup_name = backup_local_path.name
    # This must be an existing directory on the remote server.
    backup_remote_path = Path('/etc/') / backup_name
    master.run(
        args=[
            '/opt/mesosphere/bin/dcos-shell',
            'dcos-etcdctl',
            'backup',
            str(backup_remote_path),
        ],
        output=Output.LOG_AND_CAPTURE,
    )

    master.run(args=['systemctl', 'stop', 'dcos-etcd'])

    master.download_file(
        remote_path=backup_remote_path,
        local_path=backup_local_path,
    )

    master.run(args=['rm', str(backup_remote_path)])


def _do_restore(all_masters: Set[Node], backup_local_path: Path) -> None:
    backup_name = backup_local_path.name
    backup_remote_path = Path('/etc/') / backup_name

    for master in all_masters:
        master.send_file(
            local_path=backup_local_path,
            remote_path=backup_remote_path,
        )

    for master in all_masters:
        master.run(
            args=[
                '/opt/mesosphere/bin/dcos-shell',
                'dcos-etcdctl', 'restore', str(backup_remote_path),
            ],
            output=Output.LOG_AND_CAPTURE,
        )

    for master in all_masters:
        master.run(args=['systemctl', 'start', 'dcos-etcd'])


class EtcdClient():
    """interact etcd through CLI on master nodes."""
    def __init__(self, all_masters: Set[Node]) -> None:
        self.masters = all_masters

    def put(self, key: str, value: str) -> None:
        """assigns the value to the key.

        etcd is not exposed outside of the DC/OS cluster,so we have to execute
        etcdctl inside the DC/OS cluster, on a master in our case.
        `master.dcos.thisdcos.directory:2379` is the endpoint that etcd
        cluster is exposed, hence we use this endpoint to set a value to a key
        """
        master = self.masters[0]
        master.run(
            args=[
                '/opt/mesosphere/bin/dcos-shell',
                'etcdctl',
                '--endpoints="http://master.dcos.thisdcos.directory:2379',
                'put',
                key,
                value,
            ],
        )

    def get_key_from_node(
            self,
            key: str,
            master_node: Node,
    ) -> subprocess.CompletedProcess:
        """gets the value of the key on given master node"""
        result = master_node.run(
            args=[
                '/opt/mesosphere/bin/dcos-shell',
                'etcdctl',
                '--endpoints="http://{}:2379'.format(
                    master_node.private_ip_address),
                'get',
                key,
            ],
            output=Output.LOG_AND_CAPTURE,
        )
        value = result.stdout.strip().decode()
        return value


def etcd_cluster_health() -> bool:
    return True


@pytest.fixture()
def etcd_client(three_master_cluster: Cluster):
    etcd_client = EtcdClient(three_master_cluster)
    return etcd_client


class TestEtcdBackup:
    def test_snapshot_backup_and_restore(
        self,
        three_master_cluster: Cluster,
        etcd_client: EtcdClient,
        tmp_path: Path,
        request: SubRequest,
        log_dir: Path,
    ) -> None:

        test_key, test_val = "foo", "bar"
        etcd_client.put(test_key, test_val)

        random = uuid.uuid4().hex
        backup_name = 'etcd-backup-{random}.tar.gz'.format(random=random)
        backup_local_path = tmp_path / backup_name

        # Take Etcd backup from one master node.
        _do_backup(next(iter(three_master_cluster.masters)), backup_local_path)

        # Restore ZooKeeper from backup on all master nodes.
        _do_restore(three_master_cluster.masters, backup_local_path)

        # assert all etcd containers
        for master in three_master_cluster.masters:
            assert etcd_client.get(test_key, master) == test_val

        # Assert DC/OS is intact.
        wait_for_dcos_oss(
            cluster=three_master_cluster,
            request=request,
            log_dir=log_dir,
        )
