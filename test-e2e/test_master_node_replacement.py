"""
Tests for replacing master nodes.
"""

import textwrap
import uuid
from pathlib import Path
from typing import Iterator

import docker
import pytest
from _pytest.fixtures import SubRequest
from cluster_helpers import wait_for_dcos_oss
from conditional import E2E_SAFE_DEFAULT, escape, only_changed, trailing_path
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Output, Role
from docker.models.networks import Network


@pytest.fixture()
def docker_network_three_available_addresses() -> Iterator[Network]:
    """
    Return a custom Docker network with 3 assignable IP addresses.
    """
    # We want to return a Docker network with only three assignable IP
    # addresses.
    # To do this, we create a network with 8 IP addresses, where 5 are
    # reserved.
    #
    # Why we have 8 IP addresses available:
    # * The IP range is "172.28.0.0/29"
    # * We get 2 ^ (32 - 29) = 8 IP addresses
    #
    # The 8 IP addresses in the IPAM Pool are:
    # * 172.28.0.0 (reserved because this is the subnet identifier)
    # * 172.28.0.1 (reserved because this is the gateway address)
    # * 172.28.0.2 (available)
    # * 172.28.0.3 (available)
    # * 172.28.0.4 (available)
    # * 172.28.0.5 (reserved because we reserve this with `aux_addresses`)
    # * 172.28.0.6 (reserved because we reserve this with `aux_addresses`)
    # * 172.28.0.7 (reserved because this is the broadcast address)
    client = docker.from_env(version='auto')
    aux_addresses = {
        'reserved_address_0': '172.28.0.5',
        'reserved_address_1': '172.28.0.6',
    }
    ipam_pool = docker.types.IPAMPool(
        subnet='172.28.0.0/29',
        iprange='172.28.0.0/29',
        gateway='172.28.0.1',
        aux_addresses=aux_addresses,
    )
    network = client.networks.create(
        name='dcos-e2e-network-{random}'.format(random=uuid.uuid4()),
        driver='bridge',
        ipam=docker.types.IPAMConfig(pool_configs=[ipam_pool]),
        attachable=False,
    )
    try:
        yield network
    finally:
        network.remove()


@pytest.mark.skipif(
    only_changed(E2E_SAFE_DEFAULT + [
        'packages/dcos-integration-test/**',
        # All e2e tests safe except this test
        'test-e2e/test_*', '!' + escape(trailing_path(__file__, 2)),
    ]),
    reason='Only safe files modified',
)
def test_replace_all_static(
    artifact_path: Path,
    docker_network_three_available_addresses: Network,
    tmp_path: Path,
    request: SubRequest,
    log_dir: Path,
) -> None:
    """
    In a cluster with an Exhibitor backend consisting of a static ZooKeeper
    ensemble, after removing one master, and then adding another master with
    the same IP address, the cluster will get to a healthy state. This is
    repeated until all masters in the original cluster have been replaced.
    The purpose of this test is to assert that the ``node-poststart``
    procedure correctly prevents a master node replacement from being performed
    too quickly. A new master node should only become part of the cluster if
    there are no more underreplicated ranges reported by CockroachDB.

    Permanent CockroachDB data loss and a potential breakage of DC/OS occurs
    when a second master node is taken down for replacement while CockroachDB
    is recovering and there are still underreplicated ranges due to a recent
    other master node replacement.
    """
    docker_backend = Docker(network=docker_network_three_available_addresses)

    with Cluster(
        cluster_backend=docker_backend,
        # Allocate all 3 available IP addresses in the subnet.
        masters=3,
        agents=0,
        public_agents=0,
    ) as original_cluster:
        master = next(iter(original_cluster.masters))
        result = master.run(
            args=[
                'ifconfig',
                '|', 'grep', '-B1', str(master.public_ip_address),
                '|', 'grep', '-o', r'"^\w*"',
            ],
            output=Output.LOG_AND_CAPTURE,
            shell=True,
        )
        interface = result.stdout.strip().decode()
        ip_detect_contents = textwrap.dedent(
            """\
            #!/bin/bash -e
            if [ -f /sbin/ip ]; then
               IP_CMD=/sbin/ip
            else
               IP_CMD=/bin/ip
            fi

            $IP_CMD -4 -o addr show dev {interface} | awk '{{split($4,a,"/");print a[1]}}'
            """.format(interface=interface),
        )
        ip_detect_path = tmp_path / 'ip-detect'
        ip_detect_path.write_text(data=ip_detect_contents)
        static_config = {
            'master_discovery': 'static',
            'master_list': [str(master.private_ip_address)
                            for master in original_cluster.masters],
        }
        dcos_config = {
            **original_cluster.base_config,
            **static_config,
        }
        original_cluster.install_dcos_from_path(
            dcos_installer=artifact_path,
            dcos_config=dcos_config,
            ip_detect_path=ip_detect_path,
            output=Output.LOG_AND_CAPTURE,
        )
        wait_for_dcos_oss(
            cluster=original_cluster,
            request=request,
            log_dir=log_dir,
        )
        current_cluster = original_cluster
        tmp_clusters = set()

        original_masters = original_cluster.masters

        try:
            for master_to_be_replaced in original_masters:
                # Destroy a master and free one IP address.
                original_cluster.destroy_node(node=master_to_be_replaced)

                temporary_cluster = Cluster(
                    cluster_backend=docker_backend,
                    # Allocate one container with the now free IP address.
                    masters=1,
                    agents=0,
                    public_agents=0,
                )
                tmp_clusters.add(temporary_cluster)

                # Install a new master on a new container with the same IP address.
                (new_master, ) = temporary_cluster.masters
                new_master.install_dcos_from_path(
                    dcos_installer=artifact_path,
                    dcos_config=dcos_config,
                    role=Role.MASTER,
                    ip_detect_path=ip_detect_path,
                    output=Output.LOG_AND_CAPTURE,
                )
                # Form a new cluster with the newly create master node.
                new_cluster = Cluster.from_nodes(
                    masters=current_cluster.masters.union({new_master}),
                    agents=current_cluster.agents,
                    public_agents=current_cluster.public_agents,
                )
                # The `wait_for_dcos_oss` function waits until the new master has
                # joined the cluster and all masters are healthy. Without the
                # cockroachdb check, this succeeds before all cockroachdb ranges
                # have finished replicating to the new master. That meant that the
                # next master would be replaced too quickly, while it had data that
                # was not present elsewhere in the cluster. This lead to
                # irrecoverable dataloss.  This function waits until the
                # master node is "healthy". This is a requirement for replacing the
                # next master node.
                #
                # We don't call the cockroachdb ranges check directly as the
                # purpose of this test is to ensure that when an operator follows
                # our documented procedure for replacing a master node multiple
                # times in a row (e.g. during a cluster upgrade) then the cluster
                # remains healthy throughout and afterwards.
                #
                # If we called the check directly here, we would be
                # sure the check is being called, but we would not be sure that
                # "wait_for_dcos_oss", i.e., the standard procedure for determining
                # whether a node is healthy, is sufficient to prevent the cluster
                # from breaking.
                #
                # We perform this check after every master is replaced, as that is
                # what we tell operators to do: "After installing the new master
                # node, wait until it becomes healthy before proceeding to the
                # next."
                #
                # The procedure for replacing multiple masters is documented here:
                # https://docs.mesosphere.com/1.12/installing/production/upgrading/#dcos-masters
                wait_for_dcos_oss(
                    cluster=new_cluster,
                    request=request,
                    log_dir=log_dir,
                )
                # Use the new cluster object in the next replacement iteration.
                current_cluster = new_cluster

        finally:
            for cluster in tmp_clusters:
                cluster.destroy()
