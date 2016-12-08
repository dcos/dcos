import ipaddress
import urllib.parse

import bs4
from retrying import retry

from pkgpanda.util import load_yaml


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
    @retry(stop_max_delay=20000, wait_fixed=500)
    def check_up():
        r = cluster.get('/dcos-history-service/history/last')
        assert r.status_code == 200
        # Make sure some basic fields are present from state-summary which the DC/OS
        # UI relies upon. Their exact content could vary so don't test the value.
        json = r.json()
        assert {'cluster', 'frameworks', 'slaves', 'hostname'} <= json.keys()
        assert len(json["slaves"]) == len(cluster.all_slaves)

    check_up()


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


def test_cosmos_package_add(cluster):
    def package_add_configured():
        user_config = load_yaml("/opt/mesosphere/etc/user.config.yaml")

        is_staged_uri_set = user_config.get(
            'cosmos_config',
            {}
        ).get('staged_package_storage_uri')

        is_package_uri_set = user_config.get(
            'cosmos_config',
            {}
        ).get('staged_package_storage_uri')

        return is_staged_uri_set and is_package_uri_set

    r = cluster.post(
        '/package/add',
        headers={
            'Accept': (
                'application/vnd.dcos.package.add-response+json;'
                'charset=utf-8;version=v1'
            ),
            'Content-Type': (
                'application/vnd.dcos.package.add-request+json;'
                'charset=utf-8;version=v1'
            )
        },
        json={
            'packageName': 'cassandra',
            'packageVersion': '1.0.20-3.0.10'
        }
    )

    if package_add_configured():
        # if the config is enabled then Cosmos should accept the request and
        # return 202
        assert r.status_code == 202
    else:
        # if the config is disabled then Cosmos should accept the request and
        # return Not Implemented 501
        assert r.status_code == 501


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
    r = cluster.get('/mesos/overlay-agent/overlay')
    assert r.ok, "status_code: {}, content: {}".format(r.status_code, r.content)

    # Make sure the `dcos` overlay has been configured.
    json = r.json()

    assert 'overlays' in json
    assert len(json['overlays']) == 1

    # Remove 'subnet' from the dict.
    try:
        subnet = json['overlays'][0].pop('subnet')
        try:
            allocated_subnet = ipaddress.ip_network(subnet)
            assert allocated_subnet.prefixlen == 24
            assert allocated_subnet.overlaps(ipaddress.ip_network('9.0.0.0/8')),\
                "Allocated subnet: {}".format(allocated_subnet)

        except ValueError as ex:
            raise AssertionError("Could not convert subnet(" + subnet + ") network address: " + str(ex)) from ex

    except KeyError as ex:
        raise AssertionError("Could not find key 'subnet':" + str(ex)) from ex

    # Remove 'backend' from the dict.
    try:
        backend = json['overlays'][0].pop('backend')
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

    assert json['overlays'] == dcos_overlay_network
