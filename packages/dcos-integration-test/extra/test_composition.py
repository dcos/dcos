import json
import logging
import platform
import subprocess

import dns.exception
import dns.resolver
import kazoo.client
import pytest
import requests
from dcos_test_utils.dcos_api import DcosApiSession

__maintainer__ = 'mnaboka'
__contact__ = 'dcos-cluster-ops@mesosphere.io'


@pytest.mark.first
def test_dcos_cluster_is_up() -> None:
    def _docker_info(component: str) -> str:
        # sudo is required for non-coreOS installs
        return (subprocess.check_output(['sudo', 'docker', 'version', '-f', component], timeout=60)
                .decode('utf-8')
                .rstrip()
                )

    try:
        docker_client = _docker_info('{{.Client.Version}}')
    except subprocess.TimeoutExpired:
        docker_client = "Error: docker call timed out"

    try:
        docker_server = _docker_info('{{.Server.Version}}')
    except subprocess.TimeoutExpired:
        docker_server = "Error: docker call timed out"

    cluster_environment = {
        "docker_client_version": docker_client,
        "docker_server_version": docker_server,
        "system_platform": platform.platform(),
        "system_platform_system": platform.system(),
        "system_platform_release": platform.release(),
        "system_platform_version": platform.version()
    }
    logging.info(json.dumps(cluster_environment, sort_keys=True, indent=4))


def test_leader_election(dcos_api_session: DcosApiSession) -> None:
    mesos_resolver = dns.resolver.Resolver()
    mesos_resolver.nameservers = dcos_api_session.masters
    mesos_resolver.port = 61053
    try:
        mesos_resolver.query('leader.mesos', 'A')
    except dns.exception.DNSException:
        assert False, "Cannot resolve leader.mesos"


def test_if_all_mesos_masters_have_registered(dcos_api_session: DcosApiSession) -> None:
    # Currently it is not possible to extract this information through Mesos'es
    # API, let's query zookeeper directly.
    zk_hostports = 'zk-1.zk:2181,zk-2.zk:2181,zk-3.zk:2181,zk-4.zk:2181,zk-5.zk:2181'
    zk = kazoo.client.KazooClient(hosts=zk_hostports, read_only=True)
    master_ips = []

    zk.start()
    for znode in zk.get_children("/mesos"):
        if not znode.startswith("json.info_"):
            continue
        master = json.loads(zk.get("/mesos/" + znode)[0].decode('utf-8'))
        master_ips.append(master['address']['ip'])
    zk.stop()

    assert sorted(master_ips) == dcos_api_session.masters


def test_if_all_exhibitors_are_in_sync(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/exhibitor/exhibitor/v1/cluster/status')
    assert r.status_code == 200

    correct_data = sorted(r.json(), key=lambda k: k['hostname'])

    for master_node_ip in dcos_api_session.masters:
        # This relies on the fact that Admin Router always proxies the local
        # Exhibitor.
        resp = requests.get('http://{}/exhibitor/exhibitor/v1/cluster/status'.format(master_node_ip), verify=False)
        assert resp.status_code == 200

        tested_data = sorted(resp.json(), key=lambda k: k['hostname'])
        assert correct_data == tested_data


def test_mesos_agent_role_assignment(dcos_api_session: DcosApiSession) -> None:
    state_endpoint = '/state'
    for agent in dcos_api_session.public_slaves:
        r = dcos_api_session.get(state_endpoint, host=agent, port=5051)
        assert r.json()['flags']['default_role'] == 'slave_public'
    for agent in dcos_api_session.slaves:
        r = dcos_api_session.get(state_endpoint, host=agent, port=5051)
        assert r.json()['flags']['default_role'] == '*'


def test_systemd_units_are_healthy(dcos_api_session: DcosApiSession) -> None:
    """
    Test that the system is healthy at the arbitrary point in time
    that this test runs. This test has caught several issues in the past
    as it serves as a very high-level assertion about the system state.
    It seems very random, but it has proven very valuable.

    We are explicit about the list of units that are expected to be present
    in order to test against a static, known reference in order to avoid
    dynamically generated output (e.g., from /health) not matching our
    real world expectations and the test pass while errors occur silently.

    First, we loop through the nodes returned from
    the /system/health/v1/report endpoint and print the report if anything
    is unhealthy.

    Secondly, we check that the list of expected units matches the list
    of units on every node.
    """
    # Insert all the diagnostics data programmatically
    master_units = [
        'dcos-adminrouter.service',
        'dcos-cockroach.service',
        'dcos-cockroachdb-config-change.service',
        'dcos-cockroachdb-config-change.timer',
        'dcos-cosmos.service',
        'dcos-etcd.service',
        'dcos-exhibitor.service',
        'dcos-log-master.service',
        'dcos-log-master.socket',
        'dcos-logrotate-master.service',
        'dcos-logrotate-master.timer',
        'dcos-marathon.service',
        'dcos-mesos-dns.service',
        'dcos-mesos-master.service',
        'dcos-metronome.service',
        'dcos-bouncer.service',
        'dcos-bouncer-migrate-users.service',
        'dcos-ui-update-service.service',
        'dcos-ui-update-service.socket',
        'dcos-diagnostics-mesos-state.service',
        'dcos-diagnostics-mesos-state.timer',
    ]
    all_node_units = [
        'dcos-calico-bird.service',
        'dcos-calico-felix.service',
        'dcos-calico-confd.service',
        'dcos-checks-api.service',
        'dcos-checks-api.socket',
        'dcos-diagnostics.service',
        'dcos-diagnostics.socket',
        'dcos-gen-resolvconf.service',
        'dcos-gen-resolvconf.timer',
        'dcos-net.service',
        'dcos-net-watchdog.service',
        'dcos-pkgpanda-api.service',
        'dcos-checks-poststart.service',
        'dcos-checks-poststart.timer',
        'dcos-telegraf.service',
        'dcos-telegraf.socket',
        'dcos-fluent-bit.service']
    slave_units = [
        'dcos-mesos-slave.service',
        'dcos-mesos-slave.socket']
    public_slave_units = [
        'dcos-mesos-slave-public.service',
        'dcos-mesos-slave-public.socket']
    all_slave_units = [
        'dcos-adminrouter-agent.service',
        'dcos-calico-libnetwork-plugin.service',
        'dcos-docker-gc.service',
        'dcos-docker-gc.timer',
        'dcos-log-agent.service',
        'dcos-log-agent.socket',
        'dcos-logrotate-agent.service',
        'dcos-logrotate-agent.timer',
        'dcos-rexray.service']

    expected_units = {
        "master": set(all_node_units + master_units),
        "agent": set(all_node_units + all_slave_units + slave_units),
        "agent_public": set(all_node_units + all_slave_units + public_slave_units),
    }

    # Collect the dcos-diagnostics output that to determine
    # whether or not there are failed units.
    resp = dcos_api_session.get('/system/health/v1/report?cache=0')
    # We expect reading the health report to succeed.
    resp.raise_for_status()
    # Parse the response into JSON.
    health_report = resp.json()
    # The format of the /health/v1/report output is as follows:
    # {
    #     "Nodes": { ... },
    #     "Units": {
    #         "dcos-unit-foo.service": {
    #             "UnitName": "dcos-unit-foo.service",
    #             "Nodes": [
    #                 {
    #                     "Role": "agent" (or "agent_public", or "master")
    #                     "IP": "172.17.0.2",
    #                     "Host": "dcos-e2e-7dd6638e-a6f5-4276-bf6b-c9a4d6066ea4-master-2",
    #                     "Health": 0 if node is healthy, 1 if unhealthy,
    #                     "Output": {
    #                         "dcos-unit-bar.service": "" (empty string if healthy),
    #                         "dcos-unit-foo.service": "journalctl output" (if unhealthy),
    #                     }
    #                 },
    #                 ...
    #             ]
    #         }
    #     }
    # }

    # Test that all nodes have the correct set of dcos-* systemd units.
    units_per_node = {}
    exp_units_per_node = {}
    for node, node_health in health_report["Nodes"].items():
        role = node_health["Role"]  # Is one of master, agent, agent_public
        units_per_node[node] = set(node_health["Output"])
        exp_units_per_node[node] = expected_units[role]
    assert units_per_node == exp_units_per_node

    # Test that there are no unhealthy nodes.
    unhealthy_nodes = 0
    for node, node_health in health_report["Nodes"].items():
        # Assert that this node is healthy.
        if node_health["Health"] != 0:
            logging.info("Node {} was unhealthy: {}".format(
                node, json.dumps(node_health, indent=4, sort_keys=True)))
            unhealthy_nodes += 1
    assert unhealthy_nodes == 0
