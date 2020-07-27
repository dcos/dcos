"""
Tests for the etcd backup/restore via `dcos-etcdctl`.
"""
import logging
import uuid
from pathlib import Path
from shlex import split
from typing import List, Set

import pytest
from _pytest.fixtures import SubRequest
from conditional import E2E_SAFE_DEFAULT, escape, only_changed, trailing_path
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Node, Output


LOGGER = logging.getLogger(__name__)

LOCAL_ETCD_ENDPOINT_IP = "127.0.0.1"
MASTER_DNS = "master.dcos.thisdcos.directory"
DCOS_SHELL_PATH = "/opt/mesosphere/bin/dcos-shell"
ETCDCTL_PATH = "/opt/mesosphere/active/etcd/bin/etcdctl"


def get_etcdctl_with_base_args(
    cert_type: str = "root",
    endpoint_ip: str = LOCAL_ETCD_ENDPOINT_IP,
) -> List[str]:
    """Returns args including etcd endpoint and certificates if necessary.

    As dcos-etcdctl and etcdctl share the same arguments, such as endpoints,
    ever considering the certificates involved, we group these arguments to
    generate the basic items to execute either etcdctl or dcos-etcdctl
    """
    return [ETCDCTL_PATH, "--endpoints=http://{}:2379".format(endpoint_ip)]


def get_dcos_etcdctl() -> List[str]:
    return [DCOS_SHELL_PATH, "dcos-etcdctl"]


def _do_backup(master: Node, backup_local_path: Path) -> None:

    backup_name = backup_local_path.name
    # This must be an existing directory on the remote server.
    backup_remote_path = Path("/etc/") / backup_name
    dcos_etcdctl_with_args = get_dcos_etcdctl()
    dcos_etcdctl_with_args += ["backup", str(backup_remote_path)]
    master.run(
        args=dcos_etcdctl_with_args,
        output=Output.LOG_AND_CAPTURE,
    )

    master.download_file(
        remote_path=backup_remote_path,
        local_path=backup_local_path,
    )

    master.run(args=["rm", str(backup_remote_path)])


def _do_restore(all_masters: Set[Node], backup_local_path: Path) -> None:
    backup_name = backup_local_path.name
    backup_remote_path = Path("/etc/") / backup_name

    for master in all_masters:
        master.run(args=["systemctl", "stop", "dcos-etcd"])
        master.send_file(
            local_path=backup_local_path,
            remote_path=backup_remote_path,
        )

    for master in all_masters:
        dcos_etcdctl_with_args = get_dcos_etcdctl()
        dcos_etcdctl_with_args += ["restore", str(backup_remote_path)]
        master.run(
            args=dcos_etcdctl_with_args,
            output=Output.LOG_AND_CAPTURE,
        )

    # etcd instances are required to start up simultaneously to meet the
    # requirement of peer communication when starting up
    for master in all_masters:
        cmd_in_background = "nohup systemctl start dcos-etcd >/dev/null 2>&1 &"
        master.run(args=split(cmd_in_background), shell=True)


class EtcdClient():
    """Communicates with etcd thsrough CLI on master nodes."""

    def __init__(self, all_masters: Set[Node]) -> None:
        self.masters = all_masters

    def put(self, key: str, value: str) -> None:
        """assigns the value to the key.

        etcd is not exposed outside of the DC/OS cluster,so we have to execute
        etcdctl inside the DC/OS cluster, on a master in our case.
        `master.dcos.thisdcos.directory:2379` is the endpoint that etcd
        cluster is exposed, hence we use this endpoint to set a value to a key
        """
        master = list(self.masters)[0]
        etcdctl_with_args = get_etcdctl_with_base_args(endpoint_ip=MASTER_DNS)
        etcdctl_with_args += ["put", key, value]
        master.run(args=etcdctl_with_args, output=Output.LOG_AND_CAPTURE)

    def get_key_from_node(
            self,
            key: str,
            master_node: Node,
    ) -> str:
        """gets the value of the key on given master node"""
        etcdctl_with_args = get_etcdctl_with_base_args(
            endpoint_ip=str(master_node.private_ip_address))
        etcdctl_with_args += ["get", key, "--print-value-only"]
        result = master_node.run(
            args=etcdctl_with_args,
            output=Output.LOG_AND_CAPTURE,
        )
        value = result.stdout.strip().decode()
        return str(value)


@pytest.fixture()
def etcd_client(static_three_master_cluster: Cluster) -> EtcdClient:
    etcd_client = EtcdClient(static_three_master_cluster.masters)
    return etcd_client


@pytest.mark.skipif(
    only_changed(E2E_SAFE_DEFAULT + [
        # All packages safe except named packages
        'packages/**',
        '!packages/*treeinfo.json',
        '!packages/etcd/**',  # All packages safe except named packages
        # All e2e tests safe except this test
        'test-e2e/test_*', '!' + escape(trailing_path(__file__, 2)),
    ]),
    reason='Only safe files modified',
)
class TestEtcdBackup:
    def test_snapshot_backup_and_restore(
        self,
        static_three_master_cluster: Cluster,
        etcd_client: EtcdClient,
        tmp_path: Path,
        request: SubRequest,
        log_dir: Path,
    ) -> None:

        test_key, test_val = "foo", "bar"
        etcd_client.put(test_key, test_val)

        random = uuid.uuid4().hex
        backup_name = "etcd-backup-{random}.tar.gz".format(random=random)
        backup_local_path = tmp_path / backup_name

        # Take etcd backup from one master node.
        _do_backup(next(iter(static_three_master_cluster.masters)), backup_local_path)

        # Restore etcd from backup on all master nodes.
        _do_restore(static_three_master_cluster.masters, backup_local_path)

        # assert all etcd containers
        for master in static_three_master_cluster.masters:
            assert etcd_client.get_key_from_node(test_key, master) == test_val
