"""
Tests for Exhibitor quorum
"""
from pathlib import Path

import pytest
import requests
import retrying
from _pytest.fixtures import SubRequest
from conditional import E2E_SAFE_DEFAULT, only_changed
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Node, Output


@retrying.retry(wait_fixed=2500, stop_max_delay=120000)
def wait_for_zookeeper_serving(master: Node, count: int) -> None:
    """
    Check that ZooKeeper has `count` serving nodes.
    """
    url = 'http://{}:8181/exhibitor/v1/cluster/status'.format(master.public_ip_address)
    r = requests.get(url)
    r.raise_for_status()
    nodes = r.json()
    print(nodes)
    assert len([node for node in nodes if node['description'] == 'serving']) == count


@pytest.mark.skipif(
    only_changed(E2E_SAFE_DEFAULT + [
        'packages/**', '!packages/{bootstrap,exhibitor,java}/**',  # All packages safe except named packages
        'test-e2e/test_*', '!test-e2e/test_exhibitor_quorum.py',   # All e2e tests safe except this test
    ]),
    reason='Only safe files modified',
)
class TestExhibitorQuorum:

    def test_restart_with_missing_master(
        self,
        three_master_cluster: Cluster,
        tmp_path: Path,
        request: SubRequest,
        log_dir: Path,
    ) -> None:
        """
        Bootstrap on a static master cluster can complete when ZooKeeper
        has an available quorum.
        """
        masters = iter(three_master_cluster.masters)

        master = next(masters)
        wait_for_zookeeper_serving(master, 3)

        # Shutdown ZooKeeper on one master
        master.run(
            ['systemctl', 'stop', 'dcos-exhibitor'],
            output=Output.LOG_AND_CAPTURE,
        )

        # Select another master
        master = next(masters)

        # Restart ZooKeeper on this master to prevent the bootstrap shortcut being triggered
        master.run(
            ['systemctl', 'restart', 'dcos-exhibitor'],
            output=Output.LOG_AND_CAPTURE,
        )

        # Wait till we have a healthy 2-node ZooKeeper quorum
        wait_for_zookeeper_serving(master, 2)

        # Check that bootstrap works - `dcos-cluster-id` checks the cluster id,
        # which demonstrates that consensus checking is working
        master.run(
            [
                '/opt/mesosphere/bin/dcos-shell', '/opt/mesosphere/bin/bootstrap', 'dcos-cluster-id'
            ],
            output=Output.LOG_AND_CAPTURE,
        )
