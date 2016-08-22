import json
import os
import subprocess
import logging
import time

import kazoo.client
import requests


def test_if_all_Mesos_masters_have_registered(cluster):
    # Currently it is not possible to extract this information through Mesos'es
    # API, let's query zookeeper directly.
    zk = kazoo.client.KazooClient(hosts=cluster.zk_hostports, read_only=True)
    master_ips = []

    zk.start()
    for znode in zk.get_children("/mesos"):
        if not znode.startswith("json.info_"):
            continue
        master = json.loads(zk.get("/mesos/" + znode)[0].decode('utf-8'))
        master_ips.append(master['address']['ip'])
    zk.stop()

    assert sorted(master_ips) == cluster.masters


def test_if_all_exhibitors_are_in_sync(cluster):
    r = cluster.get('/exhibitor/exhibitor/v1/cluster/status')
    assert r.status_code == 200

    correct_data = sorted(r.json(), key=lambda k: k['hostname'])

    for zk_ip in cluster.public_masters:
        resp = requests.get('http://{}:8181/exhibitor/v1/cluster/status'.format(zk_ip))
        assert resp.status_code == 200

        tested_data = sorted(resp.json(), key=lambda k: k['hostname'])
        assert correct_data == tested_data


def test_mesos_agent_role_assignment(cluster):
    state_url = cluster.scheme + '://{}:5051/state.json'
    headers = cluster._suheader(False)
    for agent in cluster.public_slaves:
        r = requests.get(state_url.format(agent), headers=headers)
        assert r.json()['flags']['default_role'] == 'slave_public'
    for agent in cluster.slaves:
        r = requests.get(state_url.format(agent), headers=headers)
        assert r.json()['flags']['default_role'] == '*'


def test_signal_service(cluster):
    """
    signal-service runs on an hourly timer, this test runs it as a one-off
    and pushes the results to the test_server app for easy retrieval
    """
    # This is due to caching done by 3DT / Signal service
    # We're going to remove this soon: https://mesosphere.atlassian.net/browse/DCOS-9050
    time.sleep(61)
    dcos_version = os.getenv("DCOS_VERSION", "")
    signal_config = open('/opt/mesosphere/etc/dcos-signal-config.json', 'r')
    signal_config_data = json.loads(signal_config.read())
    customer_key = signal_config_data.get('customer_key', '')
    cluster_id_file = open('/var/lib/dcos/cluster-id')
    cluster_id = cluster_id_file.read().strip()

    subprocess.call(["/usr/bin/logger", "3dt-testing-starting-now"])
    print("Version: ", dcos_version)
    print("Customer Key: ", customer_key)
    print("Cluster ID: ", cluster_id)

    raw_data = cluster.get('/system/health/v1/report')
    signal_results = subprocess.check_output(["/opt/mesosphere/bin/dcos-signal", "-test"], universal_newlines=True)
    r_data = json.loads(signal_results)
    subprocess.call(["/usr/bin/logger", "3dt-testing-ending-now"])

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
        'provider': cluster.provider,
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
        'exhibitor-service',
        'history-service',
        'logrotate-master-service',
        'logrotate-master-timer',
        'marathon-service',
        'mesos-dns-service',
        'mesos-master-service',
        'metronome-service',
        'signal-service']
    all_node_units = [
        '3dt-service',
        'epmd-service',
        'gen-resolvconf-service',
        'gen-resolvconf-timer',
        'minuteman-service',
        'navstar-service',
        'pkgpanda-api-service',
        'pkgpanda-api-socket',
        'signal-timer',
        'spartan-service',
        'spartan-watchdog-service',
        'spartan-watchdog-timer']
    slave_units = [
        'mesos-slave-service',
        'vol-discovery-priv-agent-service']
    public_slave_units = [
        'mesos-slave-public-service',
        'vol-discovery-pub-agent-service']
    all_slave_units = [
        '3dt-socket',
        'adminrouter-agent-service',
        'adminrouter-agent-reload-service',
        'adminrouter-agent-reload-timer',
        'logrotate-agent-service',
        'logrotate-agent-timer',
        'rexray-service']

    master_units.append('oauth-service')

    for unit in master_units:
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-total".format(unit)] = len(cluster.masters)
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0
    for unit in all_node_units:
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-total".format(unit)] = len(
            cluster.all_slaves+cluster.masters)
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0
    for unit in slave_units:
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-total".format(unit)] = len(cluster.slaves)
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0
    for unit in public_slave_units:
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-total".format(unit)] = len(cluster.public_slaves)
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0
    for unit in all_slave_units:
        exp_data['diagnostics']['properties']["health-unit-dcos-{}-total".format(unit)] = len(cluster.all_slaves)
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
        logging.info('System report: {}'.format(raw_data.json()))
        raise err
