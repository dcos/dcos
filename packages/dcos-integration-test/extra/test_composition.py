import json
import logging
import os
import platform
import subprocess

import dns.exception
import dns.resolver
import kazoo.client
import pytest
import requests

from test_helpers import get_expanded_config

__maintainer__ = 'mnaboka'
__contact__ = 'dcos-cluster-ops@mesosphere.io'


@pytest.mark.first
def test_dcos_cluster_is_up():
    def _docker_info(component):
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


def test_leader_election(dcos_api_session):
    mesos_resolver = dns.resolver.Resolver()
    mesos_resolver.nameservers = dcos_api_session.masters
    mesos_resolver.port = 61053
    try:
        mesos_resolver.query('leader.mesos', 'A')
    except dns.exception.DNSException:
        assert False, "Cannot resolve leader.mesos"


def test_if_all_mesos_masters_have_registered(dcos_api_session):
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


def test_if_all_exhibitors_are_in_sync(dcos_api_session):
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


def test_mesos_agent_role_assignment(dcos_api_session):
    state_endpoint = '/state'
    for agent in dcos_api_session.public_slaves:
        r = dcos_api_session.get(state_endpoint, host=agent, port=5051)
        assert r.json()['flags']['default_role'] == 'slave_public'
    for agent in dcos_api_session.slaves:
        r = dcos_api_session.get(state_endpoint, host=agent, port=5051)
        assert r.json()['flags']['default_role'] == '*'


def test_systemd_units_are_healthy(dcos_api_session) -> None:
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
        'dcos-signal.service',
        'dcos-signal.timer',
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

    # Collect the dcos-diagnostics output that `dcos-signal` uses to determine
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


def test_signal_service(dcos_api_session):
    """
    signal-service runs on an hourly timer, this test runs it as a one-off
    and pushes the results to the test_server app for easy retrieval

    When this test fails due to `dcos-checks-poststart-service-unhealthy`,
    consider that the issue may be due to check timeouts which are too low.
    """
    # This is due to caching done by dcos-diagnostics / Signal service
    # We're going to remove this soon: https://mesosphere.atlassian.net/browse/DCOS-9050
    dcos_version = os.environ["DCOS_VERSION"]
    with open('/opt/mesosphere/etc/dcos-signal-config.json', 'r') as f:
        signal_config_data = json.load(f)
    customer_key = signal_config_data.get('customer_key', '')
    enabled = signal_config_data.get('enabled', 'false')
    with open('/var/lib/dcos/cluster-id', 'r') as f:
        cluster_id = f.read().strip()

    if enabled == 'false':
        pytest.skip('Telemetry disabled in /opt/mesosphere/etc/dcos-signal-config.json... skipping test')

    logging.info("Version: " + dcos_version)
    logging.info("Customer Key: " + customer_key)
    logging.info("Cluster ID: " + cluster_id)

    signal_results = subprocess.check_output(["/opt/mesosphere/bin/dcos-signal", "-test"], universal_newlines=True)
    r_data = json.loads(signal_results)

    resp = dcos_api_session.get('/system/health/v1/report?cache=0')
    # We expect reading the health report to succeed.
    resp.raise_for_status()
    # Parse the response into JSON.
    health_report = resp.json()
    # Reformat the /health json into the expected output format for dcos-signal.
    units_health = {}
    for unit, unit_health in health_report["Units"].items():
        unhealthy = 0
        for node_health in unit_health["Nodes"]:
            for output_unit, output in node_health["Output"].items():
                if unit != output_unit:
                    # This is the output of some unrelated unit, ignore.
                    continue
                if output == "":
                    # This unit is healthy on this node.
                    pass
                else:
                    # This unit is unhealthy on this node.
                    unhealthy += 1
        prefix = "health-unit-{}".format(unit.replace('.', '-'))
        units_health.update({
            "{}-total".format(prefix): len(unit_health["Nodes"]),
            "{}-unhealthy".format(prefix): unhealthy,
        })

    exp_data = {
        'diagnostics': {
            'event': 'health',
            'anonymousId': cluster_id,
            'properties': units_health,
        },
        'cosmos': {
            'event': 'package_list',
            'anonymousId': cluster_id,
            'properties': {}
        },
        'mesos': {
            'event': 'mesos_track',
            'anonymousId': cluster_id,
            'properties': {}
        }
    }

    expanded_config = get_expanded_config()
    # Generic properties which are the same between all tracks
    generic_properties = {
        'platform': expanded_config['platform'],
        'provider': expanded_config['provider'],
        'source': 'cluster',
        'clusterId': cluster_id,
        'licenseId': '',
        'customerKey': customer_key,
        'environmentVersion': dcos_version,
        'variant': 'open'
    }

    # Insert the generic property data which is the same between all signal tracks
    exp_data['diagnostics']['properties'].update(generic_properties)
    exp_data['cosmos']['properties'].update(generic_properties)
    exp_data['mesos']['properties'].update(generic_properties)

    # Check the entire hash of diagnostics data
    if r_data['diagnostics'] != exp_data['diagnostics']:
        # The optional second argument to `assert` is an error message that
        # appears to get truncated in the output. As such, we log the output
        # instead.
        logging.error("Cluster is unhealthy: {}".format(
            json.dumps(health_report, indent=4, sort_keys=True)))
        assert r_data['diagnostics'] == exp_data['diagnostics']

    # Check a subset of things regarding Mesos that we can logically check for
    framework_names = [x['name'] for x in r_data['mesos']['properties']['frameworks']]
    assert 'marathon' in framework_names
    assert 'metronome' in framework_names

    # There are no packages installed by default on the integration test, ensure the key exists
    assert len(r_data['cosmos']['properties']['package_list']) == 0
