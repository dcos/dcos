"""
Tests for ZooKeeper quorum
"""
import ipaddress
import subprocess
from pathlib import Path
from typing import Any, cast, Dict, List

import pytest
import requests
import retrying
from _pytest.fixtures import SubRequest
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Node, Output


def get_exhibitor_status(host: str) -> List[Dict[str, Any]]:
    url = 'http://{}:8181/exhibitor/v1/cluster/status'.format(host)
    r = requests.get(url)
    r.raise_for_status()
    try:
        return cast(List[Dict[str, Any]], r.json())
    except ValueError:
        print('Invalid JSON: {!r}'.format(r.content))
        raise


@retrying.retry(wait_fixed=2500, stop_max_delay=120000)
def wait_for_zookeeper_serving(master: Node, count: int) -> None:
    """
    Check that ZooKeeper has `count` serving nodes.
    """
    nodes = get_exhibitor_status(master.public_ip_address)
    print(nodes)
    assert len([node for node in nodes if node['description'] == 'serving']) == count


def check_bootstrap(node: Node) -> None:
    # Check that bootstrap works - `dcos-cluster-id` checks the cluster id,
    # which demonstrates that consensus checking is working
    node.run(
        [
            '/opt/mesosphere/bin/dcos-shell', '/opt/mesosphere/bin/bootstrap', 'dcos-cluster-id'
        ],
        output=Output.LOG_AND_CAPTURE,
    )


class TestZooKeeperQuorum:

    def test_zookeeper_quorum_static(
        self,
        static_three_master_cluster: Cluster,
        tmp_path: Path,
        request: SubRequest,
        log_dir: Path,
    ) -> None:
        """
        Bootstrap on a static master cluster can complete when ZooKeeper
        has an available quorum.
        """
        master = next(iter(static_three_master_cluster.masters))
        status = get_exhibitor_status(master.public_ip_address)
        print(status)
        leaders = [host for host in status if host['isLeader']]
        assert len(leaders) == 1, leaders
        leader_ip_address = ipaddress.ip_address(leaders[0]['hostname'])

        leader = None
        follower = []
        for master in static_three_master_cluster.masters:
            if master.private_ip_address == leader_ip_address:
                assert leader is None
                leader = master
            else:
                follower.append(master)
        assert leader is not None
        assert len(follower) == 2

        check_bootstrap(leader)

        # Shutdown ZooKeeper on one follower
        follower[0].run(
            ['systemctl', 'stop', 'dcos-exhibitor'],
            output=Output.LOG_AND_CAPTURE,
        )

        check_bootstrap(leader)

        # Shutdown ZooKeeper on the other follower
        follower[1].run(
            ['systemctl', 'stop', 'dcos-exhibitor'],
            output=Output.LOG_AND_CAPTURE,
        )

        # With 1 server bootstrap does not work
        with pytest.raises(subprocess.CalledProcessError):
            check_bootstrap(leader)

        # Start ZooKeeper on one follower
        follower[0].run(
            ['systemctl', 'start', 'dcos-exhibitor'],
            output=Output.LOG_AND_CAPTURE,
        )

        # Wait till we have a healthy 2-node ZooKeeper quorum
        wait_for_zookeeper_serving(leader, 2)

        check_bootstrap(leader)

        # Shutdown ZooKeeper on the leader
        leader.run(
            ['systemctl', 'stop', 'dcos-exhibitor'],
            output=Output.LOG_AND_CAPTURE,
        )

        # With 1 server bootstrap does not work
        with pytest.raises(subprocess.CalledProcessError):
            check_bootstrap(follower[0])

        # Start ZooKeeper on the other follower
        follower[1].run(
            ['systemctl', 'start', 'dcos-exhibitor'],
            output=Output.LOG_AND_CAPTURE,
        )

        # Wait till we have a healthy 2-node ZooKeeper quorum
        wait_for_zookeeper_serving(follower[0], 2)

        check_bootstrap(follower[1])

    def test_zookeeper_quorum_dynamic(
        self,
        dynamic_three_master_cluster: Cluster,
        tmp_path: Path,
        request: SubRequest,
        log_dir: Path,
    ) -> None:
        """
        Bootstrap on a dynamic master cluster can complete when ZooKeeper
        has an available quorum.
        """
        master = next(iter(dynamic_three_master_cluster.masters))
        status = get_exhibitor_status(master.public_ip_address)
        print(status)
        leaders = [host for host in status if host['isLeader']]
        assert len(leaders) == 1, leaders
        leader_ip_address = ipaddress.ip_address(leaders[0]['hostname'])

        leader = None
        follower = []
        for master in dynamic_three_master_cluster.masters:
            if master.private_ip_address == leader_ip_address:
                assert leader is None
                leader = master
            else:
                follower.append(master)
        assert leader is not None
        assert len(follower) == 2

        check_bootstrap(leader)

        # Shutdown ZooKeeper on one follower
        follower[0].run(
            ['systemctl', 'stop', 'dcos-exhibitor'],
            output=Output.LOG_AND_CAPTURE,
        )

        check_bootstrap(leader)

        # Shutdown ZooKeeper on the other follower
        follower[1].run(
            ['systemctl', 'stop', 'dcos-exhibitor'],
            output=Output.LOG_AND_CAPTURE,
        )

        # With 1 server bootstrap does not work
        with pytest.raises(subprocess.CalledProcessError):
            check_bootstrap(leader)

        # Start ZooKeeper on one follower
        follower[0].run(
            ['systemctl', 'start', 'dcos-exhibitor'],
            output=Output.LOG_AND_CAPTURE,
        )

        # Wait till we have a healthy 2-node ZooKeeper quorum
        wait_for_zookeeper_serving(leader, 2)

        check_bootstrap(leader)

        # Shutdown ZooKeeper on the leader
        leader.run(
            ['systemctl', 'stop', 'dcos-exhibitor'],
            output=Output.LOG_AND_CAPTURE,
        )

        # With 1 server bootstrap does not work
        with pytest.raises(subprocess.CalledProcessError):
            check_bootstrap(follower[0])

        # Start ZooKeeper on the other follower
        follower[1].run(
            ['systemctl', 'start', 'dcos-exhibitor'],
            output=Output.LOG_AND_CAPTURE,
        )

        # Wait till we have a healthy 2-node ZooKeeper quorum
        wait_for_zookeeper_serving(follower[0], 2)

        check_bootstrap(follower[1])
