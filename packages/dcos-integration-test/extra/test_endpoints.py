import ipaddress
import urllib.parse

from typing import Any

import bs4
import pytest

from dcos_test_utils.dcos_api import DcosApiSession
from requests.exceptions import ConnectionError

__maintainer__ = 'vespian'
__contact__ = 'dcos-security@mesosphere.io'


def test_if_dcos_ui_is_up(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/')

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
        link_response = dcos_api_session.head(href)
        assert link_response.status_code == 200


def test_if_mesos_is_up(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/mesos')

    assert r.status_code == 200
    assert len(r.text) > 100
    assert '<title>Mesos</title>' in r.text


def test_if_all_mesos_slaves_have_registered(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/mesos/master/slaves')
    assert r.status_code == 200

    data = r.json()
    slaves_ips = sorted(x['hostname'] for x in data['slaves'])

    assert slaves_ips == dcos_api_session.all_slaves


def test_if_exhibitor_api_is_up(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.exhibitor.get('/exhibitor/v1/cluster/list')
    assert r.status_code == 200

    data = r.json()
    assert data["port"] > 0


def test_if_exhibitor_ui_is_up(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.exhibitor.get('/')
    assert r.status_code == 200
    assert 'Exhibitor for ZooKeeper' in r.text


def test_if_zookeeper_cluster_is_up(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/exhibitor/exhibitor/v1/cluster/status')
    assert r.status_code == 200

    data = r.json()
    serving_zks = sum(1 for x in data if x['code'] == 3)
    zks_ips = sorted(x['hostname'] for x in data)
    zks_leaders = sum(1 for x in data if x['isLeader'])

    assert zks_ips == dcos_api_session.masters
    assert serving_zks == len(dcos_api_session.masters)
    assert zks_leaders == 1


def test_if_uiconfig_is_available(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/dcos-metadata/ui-config.json')

    assert r.status_code == 200
    assert 'uiConfiguration' in r.json()


def test_if_version_is_available(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/dcos-metadata/dcos-version.json')

    assert r.status_code == 200
    assert 'version' in r.json()


def test_if_marathon_is_up(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/marathon/v2/info')

    assert r.status_code == 200
    response_json = r.json()
    assert "name" in response_json
    assert "marathon" == response_json["name"]


def test_if_marathon_ui_redir_works(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/marathon')
    assert r.status_code == 200
    assert '<title>Marathon</title>' in r.text


def test_if_srouter_service_endpoint_works(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/service/marathon/v2/info')

    assert r.status_code == 200
    assert len(r.text) > 100
    response_json = r.json()
    assert "name" in response_json
    assert "marathon" == response_json["name"]
    assert "version" in response_json


def test_if_mesos_api_is_up(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/mesos_dns/v1/version')
    assert r.status_code == 200

    data = r.json()
    assert data["Service"] == 'Mesos-DNS'


def test_if_pkgpanda_metadata_is_available(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/pkgpanda/active.buildinfo.full.json')
    assert r.status_code == 200

    data = r.json()
    assert 'mesos' in data
    assert len(data) > 5  # (prozlach) We can try to put minimal number of pacakages required


def test_if_we_have_capabilities(dcos_api_session: DcosApiSession) -> None:
    """Indirectly test that Cosmos is up since this call is handled by Cosmos.
    """
    r = dcos_api_session.get(
        '/capabilities',
        headers={
            'Accept': 'application/vnd.dcos.capabilities+json;charset=utf-8;version=v1'
        }
    )
    assert r.status_code == 200
    assert {'name': 'PACKAGE_MANAGEMENT'} in r.json()['capabilities']


def test_if_overlay_master_is_up(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/mesos/overlay-master/state')
    assert r.ok, "status_code: {}, content: {}".format(r.status_code, r.content)

    # Make sure the `dcos` and `dcos6` overlays have been configured.
    json = r.json()

    dcos_overlay_network = {
        'vtep_subnet': '44.128.0.0/20',
        'vtep_subnet6': 'fd01:a::/64',
        'vtep_mac_oui': '70:B3:D5:00:00:00',
        'overlays': [{
            'name': 'dcos',
            'subnet': '9.0.0.0/8',
            'prefix': 24
        }, {
            'name': 'dcos6',
            'subnet6': 'fd01:b::/64',
            'prefix6': 80
        }]
    }

    assert nested_match(dcos_overlay_network, json['network'])


def test_if_overlay_master_agent_is_up(dcos_api_session: DcosApiSession) -> None:
    master_response = dcos_api_session.get('/mesos/overlay-master/state')
    assert master_response.ok,\
        "status_code: {}, content: {}".format(master_response.status_code, master_response.content)

    master_overlay_json = master_response.json()

    agent_response = dcos_api_session.get('/mesos/overlay-agent/overlay')
    assert agent_response.ok,\
        "status_code: {}, content: {}".format(agent_response.status_code, agent_response.content)

    # Make sure the `dcos` and `dcos6` overlays have been configured.
    agent_overlay_json = agent_response.json()

    assert 'ip' in agent_overlay_json
    agent_ip = agent_overlay_json['ip']

    master_agent_overlays = None
    for agent in master_overlay_json['agents']:
        assert 'ip' in agent
        if agent['ip'] == agent_ip:
            assert len(agent['overlays']) == 2
            master_agent_overlays = agent['overlays']

    assert 'overlays' in agent_overlay_json
    assert len(agent_overlay_json['overlays']) == 2

    for agent_overlay in agent_overlay_json['overlays']:
        overlay_name = agent_overlay['info']['name']
        if master_agent_overlays[0]['info']['name'] == overlay_name:  # type: ignore
            _validate_dcos_overlay(overlay_name, agent_overlay, master_agent_overlays[0])  # type: ignore
        else:
            _validate_dcos_overlay(overlay_name, agent_overlay, master_agent_overlays[1])  # type: ignore


def _validate_dcos_overlay(overlay_name: str, agent_overlay: dict, master_agent_overlay: dict) -> None:

    if overlay_name == 'dcos':
        assert 'subnet' in agent_overlay
        subnet = agent_overlay.pop('subnet')
        _validate_overlay_subnet(subnet, '9.0.0.0/8', 24)
    elif overlay_name == 'dcos6':
        assert 'subnet6' in agent_overlay
        subnet6 = agent_overlay.pop('subnet6')
        _validate_overlay_subnet(subnet6, 'fd01:b::/64', 80)

    if 'mesos_bridge' in master_agent_overlay:
        try:
            agent_overlay.pop('mesos_bridge')
        except KeyError as ex:
            raise AssertionError("Could not find expected 'mesos_bridge' in agent:" + str(ex)) from ex
    else:
        # Master didn't configure a `mesos-bridge` so shouldn't be
        # seeing it in the agent as well.
        assert 'mesos_bridge' not in agent_overlay

    if 'docker_bridge' in master_agent_overlay:
        try:
            agent_overlay.pop('docker_bridge')
        except KeyError as ex:
            raise AssertionError("Could not find expected 'docker_bridge' in agent:" + str(ex)) from ex
    else:
        # Master didn't configure a `docker-bridge` so shouldn't be
        # seeing it in the agent as well.
        assert 'docker_bridge' not in agent_overlay

    assert 'backend' in agent_overlay
    backend = agent_overlay.pop('backend')
    _validate_overlay_backend(overlay_name, backend)

    expected = None
    if overlay_name == 'dcos':
        expected = {
            'info': {
                'name': 'dcos',
                'subnet': '9.0.0.0/8',
                'prefix': 24
            },
            'state': {
                'status': 'STATUS_OK'
            }
        }
    elif overlay_name == 'dcos6':
        expected = {
            'info': {
                'name': 'dcos6',
                'subnet6': 'fd01:b::/64',
                'prefix6': 80
            },
            'state': {
                'status': 'STATUS_OK'
            }
        }

    assert nested_match(expected, agent_overlay)


def _validate_overlay_subnet(agent_subnet: str, overlay_subnet: Any, prefixlen: Any) -> None:
    try:
        allocated_subnet = ipaddress.ip_network(agent_subnet)
        assert allocated_subnet.prefixlen == prefixlen
        assert allocated_subnet.overlaps(ipaddress.ip_network(overlay_subnet)),\
            "Allocated subnet: {}".format(allocated_subnet)
    except ValueError as ex:
        raise AssertionError("Could not convert subnet(" + agent_subnet + ")\
            network address: " + str(ex)) from ex


def _validate_overlay_backend(overlay_name: str, backend: dict) -> None:
    try:
        # Make sure the backend has the right VNI.
        vxlan = backend['vxlan']

        # Verify the VTEP IP is allocated from the right subnet.
        if overlay_name == 'dcos':
            vtep_ip = vxlan['vtep_ip']
            assert vtep_ip.startswith('44.128')
            assert vtep_ip.endswith('/20')

        if overlay_name == 'dcos6':
            vtep_ip6 = vxlan['vtep_ip6']
            assert vtep_ip6.startswith('fd01:a')
            assert vtep_ip6.endswith('/64')

        # Verify VTEP configuration.
        vtep_mac = vxlan['vtep_mac']
        assert vtep_mac.startswith('70:b3:d5:')

        assert vxlan['vni'] == 1024
        assert vxlan['vtep_name'] == 'vtep1024'

    except KeyError as ex:
        raise AssertionError("Could not find key :" + str(ex)) from ex


def test_if_cosmos_is_only_available_locally(dcos_api_session: DcosApiSession) -> None:
    # One should not be able to connect to the cosmos HTTP and admin ports
    # over non-lo interfaces
    msg = "Cosmos reachable from non-lo interface"
    with pytest.raises(ConnectionError, message=msg):
        dcos_api_session.get('/', host=dcos_api_session.masters[0], port=7070, scheme='http')
    with pytest.raises(ConnectionError, message=msg):
        dcos_api_session.get('/', host=dcos_api_session.masters[0], port=9990, scheme='http')

    # One should be able to connect to the cosmos HTTP and admin ports at
    # 127.0.0.1:7070 and 127.0.0.1:9990.
    # Getting HTTP error codes shows that we made it all the way to
    # cosmos which is exactly what we're testing.
    r = dcos_api_session.get('/', host="127.0.0.1", port=7070, scheme='http')
    assert r.status_code == 404

    # In this case localhost:9990/ redirects to localhost:9990/admin so we
    # we expect a 200
    r = dcos_api_session.get('/', host="127.0.0.1", port=9990, scheme='http')
    assert r.status_code == 200


def nested_match(expect: Any, value: dict) -> bool:
    if expect == value:
        return True
    if isinstance(expect, dict) and isinstance(value, dict):
        for k, v in expect.items():
            if k in value:
                if not nested_match(v, value[k]):
                    return False
            else:
                return False
        return True
    if isinstance(expect, list) and isinstance(value, list):
        for x, y in zip(expect, value):
            if not nested_match(x, y):
                return False
        return True
    return False
