import urllib.parse

import bs4
from retrying import retry


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
        assert 'cluster' in json
        assert 'frameworks' in json
        assert 'slaves' in json
        assert 'hostname' in json

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
