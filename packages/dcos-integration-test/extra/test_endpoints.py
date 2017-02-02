import ipaddress
import urllib.parse

import bs4


def test_if_dcos_ui_is_up(cluster):
    r = cluster.get('/')

    assert r.status_code == 200
    assert len(r.text) > 100
    assert 'DC/OS' in r.text

    # Not sure if it's really needed, seems a bit of an overkill:
    soup = bs4.BeautifulSoup(r.text, "html.parser")
    for link in soup.find_all(['link', 'a'], href=True):
        if urllib.parse.urlparse(link.attrs['href']).netloc:
            # Relative URLs only, others are to complex to handle here
            continue
        # Some links might start with a dot (e.g. ./img/...). Remove.
        href = link.attrs['href'].lstrip('.')
        link_response = cluster.head(href)
        assert link_response.status_code == 200


def test_if_mesos_is_up(cluster):
    r = cluster.get('/mesos')

    assert r.status_code == 200
    assert len(r.text) > 100
    assert '<title>Mesos</title>' in r.text


def test_if_all_mesos_slaves_have_registered(cluster):
    r = cluster.get('/mesos/master/slaves')
    assert r.status_code == 200

    data = r.json()
    slaves_ips = sorted(x['hostname'] for x in data['slaves'])

    assert slaves_ips == cluster.all_slaves


def test_if_exhibitor_api_is_up(cluster):
    r = cluster.get('/exhibitor/exhibitor/v1/cluster/list')
    assert r.status_code == 200

    data = r.json()
    assert data["port"] > 0


def test_if_exhibitor_ui_is_up(cluster):
    r = cluster.get('/exhibitor')
    assert r.status_code == 200
    assert 'Exhibitor for ZooKeeper' in r.text


def test_if_zookeeper_cluster_is_up(cluster):
    r = cluster.get('/exhibitor/exhibitor/v1/cluster/status')
    assert r.status_code == 200

    data = r.json()
    serving_zks = sum(1 for x in data if x['code'] == 3)
    zks_ips = sorted(x['hostname'] for x in data)
    zks_leaders = sum(1 for x in data if x['isLeader'])

    assert zks_ips == cluster.masters
    assert serving_zks == len(cluster.masters)
    assert zks_leaders == 1


def test_if_uiconfig_is_available(cluster):
    r = cluster.get('/dcos-metadata/ui-config.json')

    assert r.status_code == 200
    assert 'uiConfiguration' in r.json()


def test_if_dcos_history_service_is_up(cluster):
    r = cluster.get('/dcos-history-service/ping')

    assert r.status_code == 200
    assert 'pong' == r.text


def test_if_marathon_ui_is_up(cluster):
    r = cluster.get('/marathon/ui/')

    assert r.status_code == 200
    assert len(r.text) > 100
    assert '<title>Marathon</title>' in r.text


def test_if_srouter_service_endpoint_works(cluster):
    r = cluster.get('/service/marathon/ui/')

    assert r.status_code == 200
    assert len(r.text) > 100
    assert '<title>Marathon</title>' in r.text


def test_if_mesos_api_is_up(cluster):
    r = cluster.get('/mesos_dns/v1/version')
    assert r.status_code == 200

    data = r.json()
    assert data["Service"] == 'Mesos-DNS'


def test_if_pkgpanda_metadata_is_available(cluster):
    r = cluster.get('/pkgpanda/active.buildinfo.full.json')
    assert r.status_code == 200

    data = r.json()
    assert 'mesos' in data
    assert len(data) > 5  # (prozlach) We can try to put minimal number of pacakages required


def test_if_dcos_history_service_is_getting_data(cluster):
    r = cluster.get('/dcos-history-service/history/last')
    assert r.status_code == 200
    # Make sure some basic fields are present from state-summary which the DC/OS
    # UI relies upon. Their exact content could vary so don't test the value.
    json = r.json()
    assert 'cluster' in json
    assert 'frameworks' in json
    assert 'slaves' in json
    assert 'hostname' in json


def test_if_we_have_capabilities(cluster):
    """Indirectly test that Cosmos is up since this call is handled by Cosmos.
    """
    r = cluster.get(
        '/capabilities',
        headers={
            'Accept': 'application/vnd.dcos.capabilities+json;charset=utf-8;version=v1'
        }
    )
    assert r.status_code == 200
    assert {'name': 'PACKAGE_MANAGEMENT'} in r.json()['capabilities']


def test_if_overlay_master_is_up(cluster):
    r = cluster.get('/mesos/overlay-master/state')
    assert r.ok, "status_code: {}, content: {}".format(r.status_code, r.content)

    # Make sure the `dcos` overlay has been configured.
    json = r.json()

    dcos_overlay_network = {
        'vtep_subnet': '44.128.0.0/20',
        'vtep_mac_oui': '70:B3:D5:00:00:00',
        'overlays': [
            {
                'name': 'dcos',
                'subnet': '9.0.0.0/8',
                'prefix': 24
            }
        ]
    }

    assert json['network'] == dcos_overlay_network


def test_if_overlay_master_agent_is_up(cluster):
    master_response = cluster.get('/mesos/overlay-master/state')
    assert master_response.ok,\
        "status_code: {}, content: {}".format(master_response.status_code, master_response.content)

    master_overlay_json = master_response.json()

    agent_response = cluster.get('/mesos/overlay-agent/overlay')
    assert agent_response.ok, "status_code: {}, content: {}".format(agent_response.status_code, agent_response.content)

    # Make sure the `dcos` overlay has been configured.
    agent_overlay_json = agent_response.json()

    assert 'ip' in agent_overlay_json
    agent_ip = agent_overlay_json['ip']

    assert 'overlays' in agent_overlay_json
    assert len(agent_overlay_json['overlays']) == 1

    agent_dcos_overlay = agent_overlay_json['overlays'][0]
    # Remove 'subnet' from the dict.
    try:
        subnet = agent_dcos_overlay.pop('subnet')
        try:
            allocated_subnet = ipaddress.ip_network(subnet)
            assert allocated_subnet.prefixlen == 24
            assert allocated_subnet.overlaps(ipaddress.ip_network('9.0.0.0/8')),\
                "Allocated subnet: {}".format(allocated_subnet)

        except ValueError as ex:
            raise AssertionError("Could not convert subnet(" + subnet + ") network address: " + str(ex)) from ex

    except KeyError as ex:
        raise AssertionError("Could not find key 'subnet':" + str(ex)) from ex

    # Get the Mesos and Docker bridge configuration for this agent from
    # Master.
    agent_overlay = None
    for agent in master_overlay_json['agents']:
        assert 'ip' in agent
        if agent['ip'] == agent_ip:
            assert len(agent['overlays']) == 1
            agent_overlay = agent['overlays'][0]

    # Pop mesos and docker bridge if they have been configured on the
    # Master for this agent.
    if 'mesos_bridge' in agent_overlay:
        try:
            agent_dcos_overlay.pop('mesos_bridge')
        except KeyError as ex:
            raise AssertionError("Could not find expected 'mesos_bridge' in agent:" + str(ex)) from ex
    else:
        # Master didn't configure a `mesos-bridge` so shouldn't be
        # seeing it in the agent as well.
        assert 'mesos_bridge' not in agent_dcos_overlay

    if 'docker_bridge' in agent_overlay:
        try:
            agent_dcos_overlay.pop('docker_bridge')
        except KeyError as ex:
            raise AssertionError("Could not find expected 'docker_bridge' in agent:" + str(ex)) from ex
    else:
        # Master didn't configure a `docker-bridge` so shouldn't be
        # seeing it in the agent as well.
        assert 'docker_bridge' not in agent_dcos_overlay

    # Remove 'backend' from the dict.
    try:
        backend = agent_dcos_overlay.pop('backend')
        # Make sure the backend has the right VNI.
        vxlan = backend.pop('vxlan')

        # Verify the VTEP IP is allocated from the right subnet.
        vtep_ip = vxlan.pop('vtep_ip')
        assert vtep_ip.startswith('44.128')
        assert vtep_ip.endswith('/20')

        # Verify OUI of the VTEP MAC.
        vtep_mac = vxlan.pop('vtep_mac')
        assert vtep_mac.startswith('70:b3:d5:')

        expected_vxlan = {
            'vni': 1024,
            'vtep_name': 'vtep1024'
        }
        assert vxlan == expected_vxlan

    except KeyError as ex:
        raise AssertionError("Could not find key :" + str(ex)) from ex

    # We can now compare the remainder of the overlay configured on
    # the Master.
    dcos_overlay_network = [
        {
            'info': {
                'name': 'dcos',
                'subnet': '9.0.0.0/8',
                'prefix': 24
            },
            'state': {
                'status': 'STATUS_OK'
            }
        }
    ]

    assert agent_overlay_json['overlays'] == dcos_overlay_network
