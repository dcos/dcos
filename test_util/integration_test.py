import collections
import json
import logging
import os
import urllib.parse
import uuid

import boto3
import botocore.exceptions
import bs4
import dns.exception
import dns.resolver
import kazoo.client
import pytest
import requests
import retrying

LOG_LEVEL = logging.INFO
TEST_APP_NAME_FMT = '/integration-test-{}'
MESOS_DNS_ENTRY_UPDATE_TIMEOUT = 60  # in seconds
BASE_ENDPOINT_3DT = '/system/health/v1'
PORT_3DT = 1050

# If auth is enabled, by default, tests use hard-coded OAuth token
AUTH_ENABLED = os.getenv('DCOS_AUTH_ENABLED', 'true') == 'true'
# Set these to run test against a custom configured user instead
LOGIN_UNAME = os.getenv('DCOS_LOGIN_UNAME')
LOGIN_PW = os.getenv('DCOS_LOGIN_PW')

# AWS creds for volume control (not used currently)
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION')


@pytest.fixture(scope='module')
def cluster():
    assert 'DCOS_DNS_ADDRESS' in os.environ
    assert 'MASTER_HOSTS' in os.environ
    assert 'PUBLIC_MASTER_HOSTS' in os.environ
    assert 'SLAVE_HOSTS' in os.environ
    assert 'PUBLIC_SLAVE_HOSTS' in os.environ
    assert 'DNS_SEARCH' in os.environ

    # dns_search must be true or false (prevents misspellings)
    assert os.environ['DNS_SEARCH'] in ['true', 'false']

    _setup_logging()

    return Cluster(dcos_uri=os.environ['DCOS_DNS_ADDRESS'],
                   masters=os.environ['MASTER_HOSTS'].split(','),
                   public_masters=os.environ['PUBLIC_MASTER_HOSTS'].split(','),
                   slaves=os.environ['SLAVE_HOSTS'].split(','),
                   public_slaves=os.environ['PUBLIC_SLAVE_HOSTS'].split(','),
                   registry=os.environ['REGISTRY_HOST'],
                   dns_search_set=os.environ['DNS_SEARCH'])


@pytest.fixture(scope='module')
def auth_cluster(cluster):
    if not AUTH_ENABLED:
        pytest.skip("Skipped because not running against cluster with auth.")
    return cluster


def _setup_logging():
    """Setup logging for the script"""
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)
    fmt = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    logging.getLogger("requests").setLevel(logging.WARNING)


def _delete_ec2_volume(name, timeout=300):
    """Delete an EC2 EBS volume by its "Name" tag

    Args:
        timeout: seconds to wait for volume to become available for deletion

    """
    @retrying.retry(wait_fixed=30 * 1000, stop_max_delay=timeout * 1000,
                    retry_on_exception=lambda exc: isinstance(exc, botocore.exceptions.ClientError))
    def _delete_volume(volume):
        volume.delete()  # Raises ClientError if the volume is still attached.

    volumes = list(boto3.session.Session(
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    ).resource('ec2').volumes.filter(Filters=[{'Name': 'tag:Name', 'Values': [name]}]))

    if len(volumes) == 0:
        raise Exception('no volumes found with name {}'.format(name))
    elif len(volumes) > 1:
        raise Exception('multiple volumes found with name {}'.format(name))
    volume = volumes[0]

    try:
        _delete_volume(volume)
    except retrying.RetryError:
        pytest.fail("Volume destroy failed - operation was not "
                    "completed in {} seconds.".format(timeout))


class Cluster:
    @retrying.retry(wait_fixed=1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _wait_for_Marathon_up(self):
        r = self.get('/marathon/ui/')
        # resp_code >= 500 -> backend is still down probably
        if r.status_code < 500:
            logging.info("Marathon is probably up")
            return True
        else:
            msg = "Waiting for Marathon, resp code is: {}"
            logging.info(msg.format(r.status_code))
            return False

    @retrying.retry(wait_fixed=1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _wait_for_slaves_to_join(self):
        r = self.get('/mesos/master/slaves')
        if r.status_code != 200:
            msg = "Mesos master returned status code {} != 200 "
            msg += "continuing to wait..."
            logging.info(msg.format(r.status_code))
            return False
        data = r.json()
        # Check that there are all the slaves the test knows about. They are all
        # needed to pass the test.
        num_slaves = len(data['slaves'])
        if num_slaves >= len(self.all_slaves):
            msg = "Sufficient ({} >= {}) number of slaves have joined the cluster"
            logging.info(msg.format(num_slaves, self.all_slaves))
            return True
        else:
            msg = "Current number of slaves: {} < {}, continuing to wait..."
            logging.info(msg.format(num_slaves, self.all_slaves))
            return False

    @retrying.retry(wait_fixed=1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _wait_for_DCOS_history_up(self):
        r = self.get('/dcos-history-service/ping')
        # resp_code >= 500 -> backend is still down probably
        if r.status_code <= 500:
            logging.info("DC/OS History is probably up")
            return True
        else:
            msg = "Waiting for DC/OS History, resp code is: {}"
            logging.info(msg.format(r.status_code))
            return False

    @retrying.retry(wait_fixed=1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _wait_for_leader_election(self):
        mesos_resolver = dns.resolver.Resolver()
        mesos_resolver.nameservers = self.public_masters
        mesos_resolver.port = 61053
        try:
            # Yeah, we can also put it in retry_on_exception, but
            # this way we will loose debug messages
            mesos_resolver.query('leader.mesos', 'A')
        except dns.exception.DNSException as e:
            msg = "Cannot resolve leader.mesos, error string: '{}', continuing to wait"
            logging.info(msg.format(e))
            return False
        else:
            logging.info("leader.mesos dns entry is UP!")
            return True

    @retrying.retry(wait_fixed=1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _wait_for_adminrouter_up(self):
        try:
            # Yeah, we can also put it in retry_on_exception, but
            # this way we will loose debug messages
            self.get(disable_suauth=True)
        except requests.ConnectionError as e:
            msg = "Cannot connect to nginx, error string: '{}', continuing to wait"
            logging.info(msg.format(e))
            return False
        else:
            logging.info("Nginx is UP!")
            return True

    def _wait_for_DCOS(self):
        self._wait_for_leader_election()
        self._wait_for_adminrouter_up()
        self._authenticate()
        self._wait_for_Marathon_up()
        self._wait_for_slaves_to_join()
        self._wait_for_DCOS_history_up()

    def _authenticate(self):
        if AUTH_ENABLED:
            # token valid until 2036 for user albert@bekstil.net
            # {
            #   "email": "albert@bekstil.net",
            #   "email_verified": true,
            #   "iss": "https://dcos.auth0.com/",
            #   "sub": "google-oauth2|109964499011108905050",
            #   "aud": "3yF5TOSzdlI45Q1xspxzeoGBe9fNxm9m",
            #   "exp": 2090884974,
            #   "iat": 1460164974
            # }
            js = {'token': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImtpZCI6Ik9UQkVOakZFTWtWQ09VRTRPRVpGTlRNMFJrWXlRa015Tnprd1JrSkVRemRCTWpBM1FqYzVOZyJ9.eyJlbWFpbCI6ImFsYmVydEBiZWtzdGlsLm5ldCIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJpc3MiOiJodHRwczovL2Rjb3MuYXV0aDAuY29tLyIsInN1YiI6Imdvb2dsZS1vYXV0aDJ8MTA5OTY0NDk5MDExMTA4OTA1MDUwIiwiYXVkIjoiM3lGNVRPU3pkbEk0NVExeHNweHplb0dCZTlmTnhtOW0iLCJleHAiOjIwOTA4ODQ5NzQsImlhdCI6MTQ2MDE2NDk3NH0.OxcoJJp06L1z2_41_p65FriEGkPzwFB_0pA9ULCvwvzJ8pJXw9hLbmsx-23aY2f-ydwJ7LSibL9i5NbQSR2riJWTcW4N7tLLCCMeFXKEK4hErN2hyxz71Fl765EjQSO5KD1A-HsOPr3ZZPoGTBjE0-EFtmXkSlHb1T2zd0Z8T5Z2-q96WkFoT6PiEdbrDA-e47LKtRmqsddnPZnp0xmMQdTr2MjpVgvqG7TlRvxDcYc-62rkwQXDNSWsW61FcKfQ-TRIZSf2GS9F9esDF4b5tRtrXcBNaorYa9ql0XAWH5W_ct4ylRNl3vwkYKWa4cmPvOqT5Wlj9Tf0af4lNO40PQ'}  # noqa
            if LOGIN_UNAME and LOGIN_PW:
                js = {'uid': LOGIN_UNAME, 'password': LOGIN_PW}
        else:
            # no authentication required
            return

        r = requests.post(self.dcos_uri + '/acs/api/v1/auth/login', json=js)
        assert r.status_code == 200
        self.superuser_auth_header = {
            'Authorization': 'token=%s' % r.json()['token']
            }
        self.superuser_auth_cookie = r.cookies[
            'dcos-acs-auth-cookie']

    def __init__(self, dcos_uri, masters, public_masters, slaves, public_slaves, registry, dns_search_set):
        """Proxy class for DC/OS clusters.

        Args:
            dcos_uri: address for the DC/OS web UI.
            masters: list of Mesos master advertised IP addresses.
            public_masters: list of Mesos master IP addresses routable from
                the local host.
            slaves: list of Mesos slave/agent advertised IP addresses.
            registry: hostname or IP address of a private Docker registry.
            dns_search_set: string indicating that a DNS search domain is
                configured if its value is "true".
        """
        self.masters = sorted(masters)
        self.public_masters = sorted(public_masters)
        self.slaves = sorted(slaves)
        self.public_slaves = sorted(public_slaves)
        self.all_slaves = sorted(slaves+public_slaves)
        self.zk_hostports = ','.join(':'.join([host, '2181']) for host in self.public_masters)
        self.registry = registry
        self.dns_search_set = dns_search_set == 'true'

        assert len(self.masters) == len(self.public_masters)

        # URI must include scheme
        assert dcos_uri.startswith('http')

        # Make URI never end with /
        self.dcos_uri = dcos_uri.rstrip('/')

        self._wait_for_DCOS()

    @staticmethod
    def _marathon_req_headers():
        return {'Accept': 'application/json, text/plain, */*'}

    def _suheader(self, disable_suauth):
        if not disable_suauth and AUTH_ENABLED:
            return self.superuser_auth_header
        return {}

    def get(self, path="", params=None, disable_suauth=False, **kwargs):
        hdrs = self._suheader(disable_suauth)
        hdrs.update(kwargs.pop('headers', {}))
        return requests.get(
            self.dcos_uri + path, params=params, headers=hdrs, **kwargs)

    def post(self, path="", payload=None, disable_suauth=False, **kwargs):
        hdrs = self._suheader(disable_suauth)
        hdrs.update(kwargs.pop('headers', {}))
        if payload is None:
            payload = {}
        return requests.post(self.dcos_uri + path, json=payload, headers=hdrs)

    def delete(self, path="", disable_suauth=False, **kwargs):
        hdrs = self._suheader(disable_suauth)
        hdrs.update(kwargs.pop('headers', {}))
        return requests.delete(self.dcos_uri + path, headers=hdrs, **kwargs)

    def head(self, path="", disable_suauth=False):
        hdrs = self._suheader(disable_suauth)
        return requests.head(self.dcos_uri + path, headers=hdrs)

    def get_base_testapp_definition(self, docker_network_bridge=True):
        test_uuid = uuid.uuid4().hex

        docker_config = {
            'image': '{}:5000/test_server'.format(self.registry),
            'forcePullImage': True,
        }
        if docker_network_bridge:
            cmd = '/opt/test_server.py 9080'
            docker_config['network'] = 'BRIDGE'
            docker_config['portMappings'] = [{
                'containerPort':  9080,
                'hostPort': 0,
                'servicePort': 0,
                'protocol': 'tcp',
            }]
            ports = []
        else:
            cmd = '/opt/test_server.py $PORT0'
            docker_config['network'] = 'HOST'
            ports = [0]

        return {
            'id': TEST_APP_NAME_FMT.format(test_uuid),
            'container': {
                'type': 'DOCKER',
                'docker': docker_config,
            },
            'cmd': cmd,
            'ports': ports,
            'cpus': 0.1,
            'mem': 64,
            'instances': 1,
            'healthChecks':
            [
                {
                    'protocol': 'HTTP',
                    'path': '/ping',
                    'portIndex': 0,
                    'gracePeriodSeconds': 5,
                    'intervalSeconds': 10,
                    'timeoutSeconds': 10,
                    'maxConsecutiveFailures': 3
                }
            ],
            "env": {
                "DCOS_TEST_UUID": test_uuid
            },
        }, test_uuid

    def deploy_marathon_app(self, app_definition, timeout=300, check_health=True, ignore_failed_tasks=False):
        """Deploy an app to marathon

        This function deploys an an application and then waits for marathon to
        aknowledge it's successfull creation or fails the test.

        The wait for application is immediatelly aborted if Marathon returns
        nonempty 'lastTaskFailure' field. Otherwise it waits until all the
        instances reach tasksRunning and then tasksHealthy state.

        Args:
            app_definition: a dict with application definition as specified in
                            Marathon API (https://mesosphere.github.io/marathon/docs/rest-api.html#post-v2-apps)
            timeout: a time to wait for the application to reach 'Healthy' status
                     after which the test should be failed.
            check_health: wait until Marathon reports tasks as healthy before
                          returning

        Returns:
            A list of named tuples which represent service points of deployed
            applications. I.E:
                [Endpoint(host='172.17.10.202', port=10464), Endpoint(host='172.17.10.201', port=1630)]
        """
        r = self.post('/marathon/v2/apps', app_definition, headers=self._marathon_req_headers())
        assert r.ok

        @retrying.retry(wait_fixed=1000, stop_max_delay=timeout*1000,
                        retry_on_result=lambda ret: ret is None,
                        retry_on_exception=lambda x: False)
        def _pool_for_marathon_app(app_id):
            Endpoint = collections.namedtuple("Endpoint", ["host", "port"])
            # Some of the counters need to be explicitly enabled now and/or in
            # future versions of Marathon:
            req_params = (('embed', 'apps.lastTaskFailure'),
                          ('embed', 'apps.counts'))
            req_uri = '/marathon/v2/apps' + app_id

            r = self.get(req_uri, req_params, headers=self._marathon_req_headers())
            assert r.ok

            data = r.json()

            if not ignore_failed_tasks:
                assert 'lastTaskFailure' not in data['app'], (
                    'Application deployment failed, reason: {}'.format(data['app']['lastTaskFailure']['message'])
                )

            if (
                data['app']['tasksRunning'] == app_definition['instances'] and
                (not check_health or data['app']['tasksHealthy'] == app_definition['instances'])
            ):
                res = [Endpoint(t['host'], t['ports'][0]) for t in data['app']['tasks']]
                logging.info('Application deployed, running on {}'.format(res))
                return res
            else:
                logging.info('Waiting for application to be deployed %s', repr(data))
                return None

        try:
            return _pool_for_marathon_app(app_definition['id'])
        except retrying.RetryError:
            pytest.fail("Application deployment failed - operation was not "
                        "completed in {} seconds.".format(timeout))

    def destroy_marathon_app(self, app_name, timeout=300):
        """Remove a marathon app

        Abort the test if the removal was unsuccesful.

        Args:
            app_name: name of the applicatoin to remove
            timeout: seconds to wait for destruction before failing test
        """
        @retrying.retry(wait_fixed=1000, stop_max_delay=timeout*1000,
                        retry_on_result=lambda ret: not ret,
                        retry_on_exception=lambda x: False)
        def _destroy_complete(deployment_id):
            r = self.get('/marathon/v2/deployments', headers=self._marathon_req_headers())
            assert r.ok

            for deployment in r.json():
                if deployment_id == deployment.get('id'):
                    logging.info('Waiting for application to be destroyed')
                    return False
            logging.info('Application destroyed')
            return True

        r = self.delete('/marathon/v2/apps' + app_name, headers=self._marathon_req_headers())
        assert r.ok

        try:
            _destroy_complete(r.json()['deploymentId'])
        except retrying.RetryError:
            pytest.fail("Application destroy failed - operation was not "
                        "completed in {} seconds.".format(timeout))


def test_if_DCOS_UI_is_up(cluster):
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


def test_adminrouter_access_control_enforcement(auth_cluster):
    r = auth_cluster.get('/acs/api/v1', disable_suauth=True)
    assert r.status_code == 401
    assert r.headers['WWW-Authenticate'] in ('acsjwt', 'oauthjwt')
    # Make sure that this is UI's error page body,
    # including some JavaScript.
    assert '<html>' in r.text
    assert '</html>' in r.text
    assert 'window.location' in r.text
    # Verify that certain locations are forbidden to access
    # when not authed, but are reachable as superuser.
    for path in ('/mesos_dns/v1/config', '/service/marathon/', '/mesos/'):
        r = auth_cluster.get(path, disable_suauth=True)
        assert r.status_code == 401
        r = auth_cluster.get(path)
        assert r.status_code == 200

    # Test authentication with auth cookie instead of Authorization header.
    authcookie = {
        'dcos-acs-auth-cookie': auth_cluster.superuser_auth_cookie
        }
    r = auth_cluster.get(
        '/service/marathon/',
        disable_suauth=True,
        cookies=authcookie
        )
    assert r.status_code == 200


def test_logout(auth_cluster):
    """Test logout endpoint. It's a soft logout, instructing
    the user agent to delete the authentication cookie, i.e. this test
    does not have side effects on other tests.
    """
    r = auth_cluster.get('/acs/api/v1/auth/logout')
    cookieheader = r.headers['set-cookie']
    assert 'dcos-acs-auth-cookie=;' in cookieheader
    assert 'expires' in cookieheader.lower()


def test_if_Mesos_is_up(cluster):
    r = cluster.get('/mesos')

    assert r.status_code == 200
    assert len(r.text) > 100
    assert '<title>Mesos</title>' in r.text


def test_if_all_Mesos_slaves_have_registered(cluster):
    r = cluster.get('/mesos/master/slaves')
    assert r.status_code == 200

    data = r.json()
    slaves_ips = sorted(x['hostname'] for x in data['slaves'])

    assert slaves_ips == cluster.all_slaves


# Retry if returncode is False, do not retry on exceptions.
@retrying.retry(wait_fixed=2000,
                retry_on_result=lambda r: r is False,
                retry_on_exception=lambda _: False)
def test_if_srouter_slaves_endpoint_work(cluster):
    # Get currently known agents. This request is served straight from
    # Mesos (no AdminRouter-based caching is involved).
    r = cluster.get('/mesos/master/slaves')
    assert r.status_code == 200

    data = r.json()
    slaves_ids = sorted(x['id'] for x in data['slaves'])

    for slave_id in slaves_ids:
        # AdminRouter's slave endpoint internally uses cached Mesos
        # state data. That is, slave IDs of just recently joined
        # slaves can be unknown here. For those, this endpoint
        # returns a 404. Retry in this case, until this endpoint
        # is confirmed to work for all known agents.
        uri = '/slave/{}/slave%281%29/state.json'.format(slave_id)
        r = cluster.get(uri)
        if r.status_code == 404:
            return False
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert data["id"] == slave_id


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


def test_if_Exhibitor_API_is_up(cluster):
    r = cluster.get('/exhibitor/exhibitor/v1/cluster/list')
    assert r.status_code == 200

    data = r.json()
    assert data["port"] > 0


def test_if_Exhibitor_UI_is_up(cluster):
    r = cluster.get('/exhibitor')
    assert r.status_code == 200
    assert 'Exhibitor for ZooKeeper' in r.text


def test_if_ZooKeeper_cluster_is_up(cluster):
    r = cluster.get('/exhibitor/exhibitor/v1/cluster/status')
    assert r.status_code == 200

    data = r.json()
    serving_zks = sum(1 for x in data if x['code'] == 3)
    zks_ips = sorted(x['hostname'] for x in data)
    zks_leaders = sum(1 for x in data if x['isLeader'])

    assert zks_ips == cluster.masters
    assert serving_zks == len(cluster.masters)
    assert zks_leaders == 1


def test_if_all_exhibitors_are_in_sync(cluster):
    r = cluster.get('/exhibitor/exhibitor/v1/cluster/status')
    assert r.status_code == 200

    correct_data = sorted(r.json(), key=lambda k: k['hostname'])

    for zk_ip in cluster.public_masters:
        resp = requests.get('http://{}:8181/exhibitor/v1/cluster/status'.format(zk_ip))
        assert resp.status_code == 200

        tested_data = sorted(resp.json(), key=lambda k: k['hostname'])
        assert correct_data == tested_data


def test_if_uiconfig_is_available(cluster):
    r = cluster.get('/dcos-metadata/ui-config.json')

    assert r.status_code == 200
    assert 'uiConfiguration' in r.json()


def test_if_DCOSHistoryService_is_up(cluster):
    r = cluster.get('/dcos-history-service/ping')

    assert r.status_code == 200
    assert 'pong' == r.text


def test_if_Marathon_UI_is_up(cluster):
    r = cluster.get('/marathon/ui/')

    assert r.status_code == 200
    assert len(r.text) > 100
    assert '<title>Marathon</title>' in r.text


def test_if_srouter_service_endpoint_works(cluster):
    r = cluster.get('/service/marathon/ui/')

    assert r.status_code == 200
    assert len(r.text) > 100
    assert '<title>Marathon</title>' in r.text


def test_if_Mesos_API_is_up(cluster):
    r = cluster.get('/mesos_dns/v1/version')
    assert r.status_code == 200

    data = r.json()
    assert data["Service"] == 'Mesos-DNS'


def test_if_PkgPanda_metadata_is_available(cluster):
    r = cluster.get('/pkgpanda/active.buildinfo.full.json')
    assert r.status_code == 200

    data = r.json()
    assert 'mesos' in data
    assert len(data) > 5  # (prozlach) We can try to put minimal number of pacakages required


def test_if_Marathon_app_can_be_deployed(cluster):
    """Marathon app deployment integration test

    This test verifies that marathon app can be deployed, and that service points
    returned by Marathon indeed point to the app that was deployed.

    The application being deployed is a simple http server written in python.
    Please check test/dockers/test_server for more details.

    This is done by assigning an unique UUID to each app and passing it to the
    docker container as an env variable. After successfull deployment, the
    "GET /test_uuid" request is issued to the app. If the returned UUID matches
    the one assigned to test - test succeds.
    """
    app_definition, test_uuid = cluster.get_base_testapp_definition()

    service_points = cluster.deploy_marathon_app(app_definition)

    r = requests.get('http://{}:{}/test_uuid'.format(service_points[0].host,
                                                     service_points[0].port))
    if r.status_code != 200:
        msg = "Test server replied with non-200 reply: '{0} {1}. "
        msg += "Detailed explanation of the problem: {2}"
        pytest.fail(msg.format(r.status_code, r.reason, r.text))

    r_data = r.json()
    assert r_data['test_uuid'] == test_uuid

    cluster.destroy_marathon_app(app_definition['id'])


def _service_discovery_test(cluster, docker_network_bridge=True):
    """Service discovery integration test

    This test verifies if service discovery works, by comparing marathon data
    with information from mesos-dns and from containers themselves.

    This is achieved by deploying an application to marathon with two instances
    , and ["hostname", "UNIQUE"] contraint set. This should result in containers
    being deployed to two different slaves.

    The application being deployed is a simple http server written in python.
    Please check test/dockers/test_server for more details.

    Next thing is comparing the service points provided by marathon with those
    reported by mesos-dns. The tricky part here is that may take some time for
    mesos-dns to catch up with changes in the cluster.

    And finally, one of service points is verified in as-seen-by-other-containers
    fashion.

                        +------------------------+   +------------------------+
                        |          Slave 1       |   |         Slave 2        |
                        |                        |   |                        |
                        | +--------------------+ |   | +--------------------+ |
    +--------------+    | |                    | |   | |                    | |
    |              |    | |   App instance A   +------>+   App instance B   | |
    |   TC Agent   +<---->+                    | |   | |                    | |
    |              |    | |   "test server"    +<------+    "reflector"     | |
    +--------------+    | |                    | |   | |                    | |
                        | +--------------------+ |   | +--------------------+ |
                        +------------------------+   +------------------------+

    Code running on TC agent connects to one of the containers (let's call it
    "test server") and makes a POST request with IP and PORT service point of
    the second container as parameters (let's call it "reflector"). The test
    server in turn connects to other container and makes a "GET /reflect"
    request. The reflector responds with test server's IP as seen by it and
    the session UUID as provided to it by Marathon. This data is then returned
    to TC agent in response to POST request issued earlier.

    The test succeds if test UUIDs of the test server, reflector and the test
    itself match and the IP of the test server matches the service point of that
    container as reported by Marathon.
    """
    app_definition, test_uuid = cluster.get_base_testapp_definition(docker_network_bridge=docker_network_bridge)
    app_definition['instances'] = 2

    if len(cluster.slaves) >= 2:
        app_definition["constraints"] = [["hostname", "UNIQUE"], ]

    service_points = cluster.deploy_marathon_app(app_definition)

    # Verify if Mesos-DNS agrees with Marathon:
    @retrying.retry(wait_fixed=1000,
                    stop_max_delay=MESOS_DNS_ENTRY_UPDATE_TIMEOUT*1000,
                    retry_on_result=lambda ret: ret is None,
                    retry_on_exception=lambda x: False)
    def _pool_for_mesos_dns():
        r = cluster.get('/mesos_dns/v1/services/_{}._tcp.marathon.mesos'.format(
                        app_definition['id'].lstrip('/')))
        assert r.status_code == 200

        r_data = r.json()
        if r_data == [{'host': '', 'port': '', 'service': '', 'ip': ''}] or \
                len(r_data) < len(service_points):
            logging.info("Waiting for Mesos-DNS to update entries")
            return None
        else:
            logging.info("Mesos-DNS entries have been updated!")
            return r_data

    try:
        r_data = _pool_for_mesos_dns()
    except retrying.RetryError:
        msg = "Mesos DNS has failed to update entries in {} seconds."
        pytest.fail(msg.format(MESOS_DNS_ENTRY_UPDATE_TIMEOUT))

    marathon_provided_servicepoints = sorted((x.host, x.port) for x in service_points)
    mesosdns_provided_servicepoints = sorted((x['ip'], int(x['port'])) for x in r_data)
    assert marathon_provided_servicepoints == mesosdns_provided_servicepoints

    # Verify if containers themselves confirm what Marathon says:
    payload = {"reflector_ip": service_points[1].host,
               "reflector_port": service_points[1].port}
    r = requests.post('http://{}:{}/your_ip'.format(service_points[0].host,
                                                    service_points[0].port),
                      payload)
    if r.status_code != 200:
        msg = "Test server replied with non-200 reply: '{status_code} {reason}. "
        msg += "Detailed explanation of the problem: {text}"
        pytest.fail(msg.format(status_code=r.status_code, reason=r.reason,
                               text=r.text))

    r_data = r.json()
    assert r_data['reflector_uuid'] == test_uuid
    assert r_data['test_uuid'] == test_uuid
    if len(cluster.slaves) >= 2:
        # When len(slaves)==1, we are connecting through docker-proxy using
        # docker0 interface ip. This makes this assertion useless, so we skip
        # it and rely on matching test uuid between containers only.
        assert r_data['my_ip'] == service_points[0].host

    cluster.destroy_marathon_app(app_definition['id'])


def test_if_service_discovery_works_docker_bridged_network(cluster):
    return _service_discovery_test(cluster, docker_network_bridge=True)


def test_if_service_discovery_works_docker_host_network(cluster):
    return _service_discovery_test(cluster, docker_network_bridge=False)


def test_if_search_is_working(cluster):
    """Test if custom set search is working.

    Verifies that a marathon app running on the cluster can resolve names using
    searching the "search" the cluster was launched with (if any). It also tests
    that absolute searches still work, and search + things that aren't
    subdomains fails properly.

    The application being deployed is a simple http server written in python.
    Please check test/dockers/test_server for more details.
    """
    # Launch the app
    app_definition, test_uuid = cluster.get_base_testapp_definition()
    service_points = cluster.deploy_marathon_app(app_definition)

    # Get the status
    r = requests.get('http://{}:{}/dns_search'.format(service_points[0].host,
                                                      service_points[0].port))
    if r.status_code != 200:
        msg = "Test server replied with non-200 reply: '{0} {1}. "
        msg += "Detailed explanation of the problem: {2}"
        pytest.fail(msg.format(r.status_code, r.reason, r.text))

    r_data = r.json()

    # Make sure we hit the app we expected
    assert r_data['test_uuid'] == test_uuid

    expected_error = {'error': '[Errno -2] Name or service not known'}

    # Check that result matches expectations for this cluster
    if cluster.dns_search_set:
        assert r_data['search_hit_leader'] in cluster.masters
        assert r_data['always_hit_leader'] in cluster.masters
        assert r_data['always_miss'] == expected_error
    else:  # No dns search, search hit should miss.
        assert r_data['search_hit_leader'] == expected_error
        assert r_data['always_hit_leader'] in cluster.masters
        assert r_data['always_miss'] == expected_error

    cluster.destroy_marathon_app(app_definition['id'])


def test_if_DCOSHistoryService_is_getting_data(cluster):
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


# By default telemetry-net sends the metrics about once a minute
# Therefore, we wait up till 2 minutes and a bit before we give up
def test_if_minuteman_routes_to_vip(cluster, timeout=125):
    """Test if we are able to connect to a task with a vip using minuteman.
    """
    # Launch the app and proxy
    test_uuid = uuid.uuid4().hex

    app_definition = {
        'id': "/integration-test-app-with-minuteman-vip-%s" % test_uuid,
        'cpus': 0.1,
        'mem': 128,
        'ports': [10000],
        'cmd': 'touch imok && /opt/mesosphere/bin/python -mhttp.server ${PORT0}',
        'labels': {'vip_PORT0': 'tcp://1.2.3.4:5000'},
        'uris': [],
        'instances': 1,
        'healthChecks': [{
            'protocol': 'HTTP',
            'path': '/',
            'portIndex': 0,
            'gracePeriodSeconds': 5,
            'intervalSeconds': 10,
            'timeoutSeconds': 10,
            'maxConsecutiveFailures': 3
        }]
    }

    cluster.deploy_marathon_app(app_definition)

    proxy_definition = {
        'id': "/integration-test-proxy-to-minuteman-vip-%s" % test_uuid,
        'cpus': 0.1,
        'mem': 128,
        'ports': [10000],
        'cmd': 'chmod 755 ncat && ./ncat -v --sh-exec "./ncat 1.2.3.4 5000" -l $PORT0 --keep-open',
        'uris': ['https://s3.amazonaws.com/sargun-mesosphere/ncat'],
        'instances': 1,
        'healthChecks': [{
            'protocol': 'COMMAND',
            'command': {
                'value': 'test "$(curl -o /dev/null --max-time 5 -4 -w \'%{http_code}\' -s http://localhost:${PORT0}/|cut -f1 -d" ")" == 200'  # noqa
            },
            'gracePeriodSeconds': 0,
            'intervalSeconds': 5,
            'timeoutSeconds': 20,
            'maxConsecutiveFailures': 3,
            'ignoreHttp1xx': False
        }],
    }

    service_points = cluster.deploy_marathon_app(proxy_definition)

    def _ensure_routable():
        r = requests.get('http://{}:{}'.format(service_points[0].host,
                                               service_points[0].port))
        assert(r.ok)
        data = r.text
        assert 'imok' in data

    _ensure_routable()


def make_3dt_request(ip, endpoint, cluster, port=80):
    """
    a helper function to get info from 3dt endpoint. Default port is 80 for pulled data from agents.
    if a destination port in 80, that means all requests should go though adminrouter and we can re-use cluster.get
    otherwise we can query 3dt agents directly to port 1050.
    """
    if port == 80:
        assert endpoint.startswith('/'), 'endpoint {} must start with /'.format(endpoint)
        logging.info('GET {}'.format(endpoint))
        json_response = cluster.get(path=endpoint).json()
        logging.info('Response: {}'.format(json_response))
        return json_response

    url = 'http://{}:{}/{}'.format(ip, port, endpoint.lstrip('/'))
    logging.info('GET {}'.format(url))
    request = requests.get(url)
    assert request.ok
    try:
        json_response = request.json()
        logging.info('Response: {}'.format(json_response))
    except ValueError:
        logging.error('Coult not deserialized json response from {}'.format(url))
        raise
    assert len(json_response) > 0, 'json response is invalid from {}'.format(url)
    return json_response


def test_3dt_health(cluster):
    """
    test health endpoint /system/health/v1
    """
    required_fields = ['units', 'hostname', 'ip', 'dcos_version', 'node_role', 'mesos_id', '3dt_version', 'system']
    required_fields_unit = ['id', 'health', 'output', 'description', 'help', 'name']
    required_system_fields = ['memory', 'load_avarage', 'partitions', 'disk_usage']

    for host in cluster.masters + cluster.slaves:
        response = make_3dt_request(host, BASE_ENDPOINT_3DT, cluster, port=PORT_3DT)
        assert len(response) == len(required_fields), 'response must have the following fields: {}'.format(
            ', '.join(required_fields)
        )

        # validate units
        assert 'units' in response, 'units field not found'
        assert isinstance(response['units'], list), 'units field must be a list'
        assert len(response['units']) > 0, 'units field cannot be empty'
        for unit in response['units']:
            assert len(unit) == len(required_fields_unit), 'unit must have the following fields: {}'.format(
                ', '.join(required_fields_unit)
            )
            for required_field_unit in required_fields_unit:
                assert required_field_unit in unit, '{} must be in a unit repsonse'

            # id, health and description cannot be empty
            assert unit['id'], 'id field cannot be empty'
            assert unit['health'] in [0, 1], 'health field must be 0 or 1'
            assert unit['description'], 'description field cannot be empty'

        # check all required fields but units
        for required_field in required_fields[1:]:
            assert required_field in response, '{} field not found'.format(required_field)
            assert response[required_field], '{} cannot be empty'.format(required_field)

        # check system metrics
        assert len(response['system']) == len(required_system_fields), 'fields required: {}'.format(
            ', '.join(required_system_fields))

        for sys_field in required_system_fields:
            assert sys_field in response['system'], 'system metric {} is missing'.format(sys_field)
            assert response['system'][sys_field], 'system metric {} cannot be empty'.format(sys_field)


def validate_node(nodes):
    assert isinstance(nodes, list), 'input argument must be a list'
    assert len(nodes) > 0, 'input argument cannot be empty'
    required_fields = ['host_ip', 'health', 'role']

    for node in nodes:
        logging.info('check node reponse: {}'.format(node))
        assert len(node) == len(required_fields), 'node should have the following fields: {}'.format(
            ', '.join(required_fields)
        )
        for required_field in required_fields:
            assert required_field in node, '{} must be in node'.format(required_field)

        # host_ip, health, role fields cannot be empty
        assert node['health'] in [0, 1], 'health must be 0 or 1'
        assert node['host_ip'], 'host_ip cannot be empty'
        assert node['role'], 'role cannot be empty'


def test_3dt_nodes(cluster):
    """
    test a list of nodes with statuses endpoint /system/health/v1/nodes
    """
    for master in cluster.masters:
        response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes', cluster)
        assert len(response) == 1, 'nodes response must have only one field: nodes'
        assert 'nodes' in response
        assert isinstance(response['nodes'], list)
        assert len(response['nodes']) == len(cluster.masters + cluster.all_slaves), (
            'a number of nodes in response must be {}'.format(len(cluster.masters + cluster.all_slaves)))

        # test nodes
        validate_node(response['nodes'])


def test_3dt_nodes_node(cluster):
    """
    test a specific node enpoint /system/health/v1/nodes/<node>
    """
    for master in cluster.masters:
        # get a list of nodes
        response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes', cluster)
        nodes = list(map(lambda node: node['host_ip'], response['nodes']))
        logging.info('received the following nodes: {}'.format(nodes))

        for node in nodes:
            node_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes/{}'.format(node), cluster)
            validate_node([node_response])


def validate_units(units):
    assert isinstance(units, list), 'input argument must be list'
    assert len(units) > 0, 'input argument cannot be empty'
    required_fields = ['id', 'name', 'health', 'description']

    for unit in units:
        logging.info('validating unit {}'.format(unit))
        assert len(unit) == len(required_fields), 'a unit must have the following fields: {}'.format(
            ', '.join(required_fields)
        )
        for required_field in required_fields:
            assert required_field in unit, 'unit response must have field: {}'.format(required_field)

        # a unit must have all 3 fields not empty
        assert unit['id'], 'id field cannot be empty'
        assert unit['name'], 'name field cannot be empty'
        assert unit['health'] in [0, 1], 'health must be 0 or 1'
        assert unit['description'], 'description field cannot be empty'


def validate_unit(unit):
    assert isinstance(unit, dict), 'input argument must be a dict'
    logging.info('validating unit: {}'.format(unit))

    required_fields = ['id', 'health', 'output', 'description', 'help', 'name']
    assert len(unit) == len(required_fields), 'unit must have the following fields: {}'.format(
        ', '.join(required_fields)
    )
    for required_field in required_fields:
        assert required_field in unit, '{} must be in a unit'.format(required_field)

    # id, name, health, description, help should not be empty
    assert unit['id'], 'id field cannot be empty'
    assert unit['name'], 'name field cannot be empty'
    assert unit['health'] in [0, 1], 'health must be 0 or 1'
    assert unit['description'], 'description field cannot be empty'
    assert unit['help'], 'help field cannot be empty'


def test_3dt_nodes_node_units(cluster):
    """
    test a list of units from a specific node, endpoint /system/health/v1/nodes/<node>/units
    """
    for master in cluster.masters:
        # get a list of nodes
        response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes', cluster)
        nodes = list(map(lambda node: node['host_ip'], response['nodes']))
        logging.info('received the following nodes: {}'.format(nodes))

        for node in nodes:
            node_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes/{}'.format(node), cluster)
            logging.info('node reponse: {}'.format(node_response))
            units_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes/{}/units'.format(node), cluster)
            logging.info('units reponse: {}'.format(units_response))

            assert len(units_response) == 1, 'unit response should have only 1 field `units`'
            assert 'units' in units_response
            validate_units(units_response['units'])


def test_3dt_nodes_node_units_unit(cluster):
    """
    test a specific unit for a specific node, endpoint /system/health/v1/nodes/<node>/units/<unit>
    """
    for master in cluster.masters:
        response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes', cluster)
        nodes = list(map(lambda node: node['host_ip'], response['nodes']))
        for node in nodes:
            units_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes/{}/units'.format(node), cluster)
            unit_ids = list(map(lambda unit: unit['id'], units_response['units']))
            logging.info('unit ids: {}'.format(unit_ids))

            for unit_id in unit_ids:
                validate_unit(
                    make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes/{}/units/{}'.format(node, unit_id), cluster))


def test_3dt_units(cluster):
    """
    test a list of collected units, endpoint /system/health/v1/units
    """
    # get all unique unit names
    all_units = set()
    for node in cluster.masters + cluster.all_slaves:
        node_response = make_3dt_request(node, BASE_ENDPOINT_3DT, cluster, port=PORT_3DT)
        for unit in node_response['units']:
            all_units.add(unit['id'])
    logging.info('all units: {}'.format(all_units))

    # test agaist masters
    for master in cluster.masters:
        units_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units', cluster)
        validate_units(units_response['units'])

        pulled_units = list(map(lambda unit: unit['id'], units_response['units']))
        logging.info('collected units: {}'.format(pulled_units))
        assert set(pulled_units) == all_units, 'not all units have been collected by 3dt puller, missing: {}'.format(
            set(pulled_units).symmetric_difference(all_units)
        )


def test_3dt_units_unit(cluster):
    """
    test a unit response in a right format, endpoint: /system/health/v1/units/<unit>
    """
    for master in cluster.masters:
        units_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units', cluster)
        pulled_units = list(map(lambda unit: unit['id'], units_response['units']))
        for unit in pulled_units:
            unit_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units/{}'.format(unit), cluster)
            validate_units([unit_response])


def make_nodes_ip_map(cluster):
    """
    a helper function to make a map detected_ip -> external_ip
    """
    node_private_public_ip_map = {}
    for node in cluster.masters + cluster.slaves:
        detected_ip = make_3dt_request(node, BASE_ENDPOINT_3DT, cluster, port=PORT_3DT)['ip']
        node_private_public_ip_map[detected_ip] = node

    logging.info('detected ips: {}'.format(node_private_public_ip_map))
    return node_private_public_ip_map


def test_3dt_units_unit_nodes(cluster):
    """
    test a list of nodes for a specific unit, endpoint /system/health/v1/units/<unit>/nodes
    """
    nodes_ip_map = make_nodes_ip_map(cluster)

    for master in cluster.masters:
        units_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units', cluster)
        pulled_units = list(map(lambda unit: unit['id'], units_response['units']))
        for unit in pulled_units:
            nodes_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units/{}/nodes'.format(unit), cluster)
            validate_node(nodes_response['nodes'])

        # make sure dcos-mesos-master.service has master nodes and dcos-mesos-slave.service has agent nodes
        master_nodes_response = make_3dt_request(
            master, BASE_ENDPOINT_3DT + '/units/dcos-mesos-master.service/nodes', cluster)
        master_nodes = list(map(lambda node: nodes_ip_map.get(node['host_ip']), master_nodes_response['nodes']))
        logging.info('master_nodes: {}'.format(master_nodes))

        assert len(master_nodes) == len(cluster.masters), '{} != {}'.format(master_nodes, cluster.masters)
        assert set(master_nodes) == set(cluster.masters), 'a list of difference: {}'.format(
            set(master_nodes).symmetric_difference(set(cluster.masters))
        )

        agent_nodes_response = make_3dt_request(
            master, BASE_ENDPOINT_3DT + '/units/dcos-mesos-slave.service/nodes', cluster)
        agent_nodes = list(map(lambda node: nodes_ip_map.get(node['host_ip']), agent_nodes_response['nodes']))
        logging.info('aget_nodes: {}'.format(agent_nodes))
        assert len(agent_nodes) == len(cluster.slaves), '{} != {}'.format(agent_nodes, cluster.slaves)


def test_3dt_units_unit_nodes_node(cluster):
    """
    test a specific node for a specific unit, endpoint /system/health/v1/units/<unit>/nodes/<node>
    """
    required_node_fields = ['host_ip', 'health', 'role', 'output', 'help']

    for master in cluster.masters:
        units_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units', cluster)
        pulled_units = list(map(lambda unit: unit['id'], units_response['units']))
        logging.info('pulled units: {}'.format(pulled_units))
        for unit in pulled_units:
            nodes_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units/{}/nodes'.format(unit), cluster)
            pulled_nodes = list(map(lambda node: node['host_ip'], nodes_response['nodes']))
            logging.info('pulled nodes: {}'.format(pulled_nodes))
            for node in pulled_nodes:
                node_response = make_3dt_request(
                    master, BASE_ENDPOINT_3DT + '/units/{}/nodes/{}'.format(unit, node), cluster)
                logging.info('node response: {}'.format(node_response))
                assert len(node_response) == len(required_node_fields), 'required fields: {}'.format(
                    ', '.format(required_node_fields)
                )

                for required_node_field in required_node_fields:
                    assert required_node_field in node_response, 'field {} must be set'.format(required_node_field)

                # host_ip, health, role, help cannot be empty
                assert node_response['host_ip'], 'host_ip field cannot be empty'
                assert node_response['health'] in [0, 1], 'health must be 0 or 1'
                assert node_response['role'], 'role field cannot be empty'
                assert node_response['help'], 'help field cannot be empty'


def test_3dt_report(cluster):
    """
    test 3dt report endpoint /system/health/v1/report
    """
    for master in cluster.masters:
        report_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/report', cluster)
        assert 'Units' in report_response
        assert len(report_response['Units']) > 0

        assert 'Nodes' in report_response
        assert len(report_response['Nodes']) > 0


def test_signal_service(cluster):
    """
    signal-service runs on an hourly timer, this test runs it as a one-off
    and pushes the results to the test_server app for easy retrieval
    """
    test_server_app_definition, _ = cluster.get_base_testapp_definition()
    service_points = cluster.deploy_marathon_app(test_server_app_definition)

    @retrying.retry(wait_fixed=1000, stop_max_delay=120*1000)
    def wait_for_endpoint():
        """Make sure test server is available before posting to it"""
        r = requests.get('http://{}:{}/signal_test_cache'.format(
            service_points[0].host,
            service_points[0].port))
        assert r.status_code == 200

    wait_for_endpoint()

    test_cache_url = "http://{}:{}/signal_test_cache".format(service_points[0].host, service_points[0].port)
    cmd = """
data=`/opt/mesosphere/bin/dcos-signal -report-host leader.mesos -test 2> /dev/null`;
curl -H 'Content-Type: application/json' -X POST -d "$data" {};
sleep 3600
""".format(test_cache_url)

    test_uuid = uuid.uuid4().hex
    signal_app_definition = {
        'id': "/integration-test-signal-service-oneshot-%s" % test_uuid,
        'cmd': cmd,
        'cpus': 0.1,
        'mem': 64,
        'instances': 1,
        'healthChecks': [{
            'protocol': 'COMMAND',
            'command': {
                'value': 'curl {} > tmp; test -s tmp'.format(test_cache_url)
            },
            'gracePeriodSeconds': 0,
            'intervalSeconds': 10,
            'timeoutSeconds': 10,
            'maxConsecutiveFailures': 1,
            'ignoreHttp1xx': False}]
    }

    cluster.deploy_marathon_app(signal_app_definition, ignore_failed_tasks=True)

    r = requests.get(test_cache_url)

    r_data = json.loads(r.json())

    cluster.destroy_marathon_app(signal_app_definition['id'])
    cluster.destroy_marathon_app(test_server_app_definition['id'])

    exp_data = {
            'Event': 'health',
            'UserId': '',
            'ClusterId': '',
            'Properties': {
                'provider': 'onprem',
                'source': 'cluster',
                'clusterId': '',
                'customerKey': '',
                'environmentVersion': '',
                'variant': 'open'}
            }

    master_units = [
            'adminrouter-reload-service',
            'adminrouter-reload-timer',
            'adminrouter-service',
            'cluster-id-service',
            'cosmos-service',
            'exhibitor-service',
            'history-service-service',
            'marathon-service',
            'mesos-dns-service',
            'mesos-master-service',
            'signal-service',
            'logrotate-master-service',
            'logrotate-master-timer']
    all_node_units = [
            'ddt-service',
            'epmd-service',
            'gen-resolvconf-service',
            'gen-resolvconf-timer',
            'minuteman-service',
            'navstar-service',
            'signal-timer',
            'spartan-service',
            'spartan-watchdog-service',
            'spartan-watchdog-timer']
    slave_units = [
            'ports-priv-agent-service',
            'mesos-slave-service',
            'vol-discovery-priv-agent-service']
    public_slave_units = [
            'mesos-slave-public-service',
            'vol-discovery-pub-agent-service']
    all_slave_units = [
            'logrotate-agent-service',
            'logrotate-agent-timer']

    master_units.append('oauth-service')

    for unit in master_units:
        exp_data['Properties']["health-unit-dcos-{}-total".format(unit)] = len(cluster.masters)
        exp_data['Properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0
    for unit in all_node_units:
        exp_data['Properties']["health-unit-dcos-{}-total".format(unit)] = len(cluster.all_slaves+cluster.masters)
        exp_data['Properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0
    for unit in slave_units:
        exp_data['Properties']["health-unit-dcos-{}-total".format(unit)] = len(cluster.slaves)
        exp_data['Properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0
    for unit in public_slave_units:
        exp_data['Properties']["health-unit-dcos-{}-total".format(unit)] = len(cluster.public_slaves)
        exp_data['Properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0
    for unit in all_slave_units:
        exp_data['Properties']["health-unit-dcos-{}-total".format(unit)] = len(cluster.all_slaves)
        exp_data['Properties']["health-unit-dcos-{}-unhealthy".format(unit)] = 0

    # Cluster ID is uncheckable as this runs on an agent
    r_data['ClusterId'] = ''
    r_data['Properties']['clusterId'] = ''

    assert r_data == exp_data


def test_mesos_agent_role_assignment(cluster):
    for agent in cluster.public_slaves:
        r = requests.get('http://{}:5051/state.json'.format(agent))
        assert r.json()['flags']['default_role'] == 'slave_public'
    for agent in cluster.slaves:
        r = requests.get('http://{}:5051/state.json'.format(agent))
        assert r.json()['flags']['default_role'] == '*'
