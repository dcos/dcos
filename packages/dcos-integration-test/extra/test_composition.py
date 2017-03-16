import json
import logging
import os
import subprocess

import dns.exception
import dns.resolver
import kazoo.client
import pytest
import requests

from test_helpers import dcos_config

from pkgpanda.util import load_json, load_string


@pytest.mark.first
def test_dcos_cluster_is_up(dcos_api_session):
    pass


def test_leader_election(dcos_api_session):
    mesos_resolver = dns.resolver.Resolver()
    mesos_resolver.nameservers = dcos_api_session.public_masters
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

    for zk_ip in dcos_api_session.public_masters:
        resp = requests.get('http://{}:8181/exhibitor/v1/cluster/status'.format(zk_ip))
        assert resp.status_code == 200

        tested_data = sorted(resp.json(), key=lambda k: k['hostname'])
        assert correct_data == tested_data


def test_mesos_agent_role_assignment(dcos_api_session):
    state_endpoint = '/state.json'
    for agent in dcos_api_session.public_slaves:
        r = dcos_api_session.get(state_endpoint, host=agent, port=5051)
        assert r.json()['flags']['default_role'] == 'slave_public'
    for agent in dcos_api_session.slaves:
        r = dcos_api_session.get(state_endpoint, host=agent, port=5051)
        assert r.json()['flags']['default_role'] == '*'


def test_signal_service(dcos_api_session):
    """
    signal-service runs on an hourly timer, this test runs it as a one-off
    and pushes the results to the test_server app for easy retrieval
    """
    # This is due to caching done by 3DT / Signal service
    # We're going to remove this soon: https://mesosphere.atlassian.net/browse/DCOS-9050
    dcos_version = os.environ["DCOS_VERSION"]
    signal_config_data = load_json('/opt/mesosphere/etc/dcos-signal-config.json')
    customer_key = signal_config_data.get('customer_key', '')
    enabled = signal_config_data.get('enabled', 'false')
    cluster_id = load_string('/var/lib/dcos/cluster-id').strip()

    if enabled == 'false':
        pytest.skip('Telemetry disabled in /opt/mesosphere/etc/dcos-signal-config.json... skipping test')

    logging.info("Version: " + dcos_version)
    logging.info("Customer Key: " + customer_key)
    logging.info("Cluster ID: " + cluster_id)

    direct_report = dcos_api_session.get('/system/health/v1/report?cache=0')
    signal_results = subprocess.check_output(["/opt/mesosphere/bin/dcos-signal", "-test"], universal_newlines=True)
    r_data = json.loads(signal_results)

    exp_data = {
        'diagnostics': {
            'event': 'health',
            'anonymousId': cluster_id,
            'properties': {}
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

    # Generic properties which are the same between all tracks
    generic_properties = {
        'platform': dcos_config['platform'],
        'provider': dcos_config['provider'],
        'source': 'cluster',
        'clusterId': cluster_id,
        'customerKey': customer_key,
        'environmentVersion': dcos_version,
        'variant': 'open'
    }

    # Insert the generic property data which is the same between all signal tracks
    exp_data['diagnostics']['properties'].update(generic_properties)
    exp_data['cosmos']['properties'].update(generic_properties)
    exp_data['mesos']['properties'].update(generic_properties)

    # Insert all the diagnostics data programmatically
    master_units = [
        'adminrouter-service',
        'adminrouter-reload-service',
        'adminrouter-reload-timer',
        'cosmos-service',
        'metrics-master-service',
        'metrics-master-socket',
        'exhibitor-service',
        'history-service',
        'log-master-service',
        'log-master-socket',
        'logrotate-master-service',
        'logrotate-master-timer',
        'marathon-service',
        'mesos-dns-service',
        'mesos-master-service',
        'metronome-service',
        'signal-service']
    all_node_units = [
        '3dt-service',
        '3dt-socket',
        'epmd-service',
        'gen-resolvconf-service',
        'gen-resolvconf-timer',
        'navstar-service',
        'pkgpanda-api-service',
        'pkgpanda-api-socket',
        'signal-timer',
        'spartan-service',
        'spartan-watchdog-service',
        'spartan-watchdog-timer']
    slave_units = [
        'mesos-slave-service']
    public_slave_units = [
        'mesos-slave-public-service']
    all_slave_units = [
        'docker-gc-service',
        'docker-gc-timer',
        'metrics-agent-service',
        'metrics-agent-socket',
        'adminrouter-agent-service',
        'adminrouter-agent-reload-service',
        'adminrouter-agent-reload-timer',
        'log-agent-service',
        'log-agent-socket',
        'logrotate-agent-service',
        'logrotate-agent-timer',
        'rexray-service']

    master_units.append('oauth-service')

    for unit in master_units:
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-total".format(unit)] = len(dcos_api_session.masters)
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0
    for unit in all_node_units:
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-total".format(unit)] = len(
            dcos_api_session.all_slaves + dcos_api_session.masters)
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0
    for unit in slave_units:
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-total".format(unit)] = len(dcos_api_session.slaves)
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0
    for unit in public_slave_units:
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-total".format(unit)] \
            = len(dcos_api_session.public_slaves)
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0
    for unit in all_slave_units:
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-total".format(unit)] \
            = len(dcos_api_session.all_slaves)
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0

    def check_signal_data():
        # Check the entire hash of diagnostics data
        assert r_data['diagnostics'] == exp_data['diagnostics']
        # Check a subset of things regarding Mesos that we can logically check for
        framework_names = [x['name'] for x in r_data['mesos']['properties']['frameworks']]
        assert 'marathon' in framework_names
        assert 'metronome' in framework_names
        # There are no packages installed by default on the integration test, ensure the key exists
        assert len(r_data['cosmos']['properties']['package_list']) == 0

    try:
        check_signal_data()
    except AssertionError as err:
        logging.info('System report: {}'.format(direct_report.json()))
        raise err
