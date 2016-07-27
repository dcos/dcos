import collections
import logging
import os
import uuid
from subprocess import check_call

import dns.exception
import dns.resolver
import pytest
import requests
import retrying

LOG_LEVEL = logging.INFO
TEST_APP_NAME_FMT = '/integration-test-{}'
# If auth is enabled, by default, tests use hard-coded OAuth token
AUTH_ENABLED = os.getenv('DCOS_AUTH_ENABLED', 'true') == 'true'
# Set these to run test against a custom configured user instead
LOGIN_UNAME = os.getenv('DCOS_LOGIN_UNAME')
LOGIN_PW = os.getenv('DCOS_LOGIN_PW')


@pytest.fixture(scope='module')
def cluster():
    assert 'DCOS_DNS_ADDRESS' in os.environ
    assert 'MASTER_HOSTS' in os.environ
    assert 'PUBLIC_MASTER_HOSTS' in os.environ
    assert 'SLAVE_HOSTS' in os.environ
    assert 'PUBLIC_SLAVE_HOSTS' in os.environ
    assert 'DNS_SEARCH' in os.environ
    assert 'DCOS_PROVIDER' in os.environ

    # dns_search must be true or false (prevents misspellings)
    assert os.environ['DNS_SEARCH'] in ['true', 'false']

    assert os.environ['DCOS_PROVIDER'] in ['onprem', 'aws', 'azure']

    _setup_logging()

    return Cluster(dcos_uri=os.environ['DCOS_DNS_ADDRESS'],
                   masters=os.environ['MASTER_HOSTS'].split(','),
                   public_masters=os.environ['PUBLIC_MASTER_HOSTS'].split(','),
                   slaves=os.environ['SLAVE_HOSTS'].split(','),
                   public_slaves=os.environ['PUBLIC_SLAVE_HOSTS'].split(','),
                   registry=os.getenv('REGISTRY_HOST'),
                   dns_search_set=os.environ['DNS_SEARCH'],
                   provider=os.environ['DCOS_PROVIDER'],
                   auth_enabled=AUTH_ENABLED)


def _setup_logging():
    """Setup logging for the script"""
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)
    fmt = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    logging.getLogger("requests").setLevel(logging.WARNING)


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

    # Retry if returncode is False, do not retry on exceptions.
    @retrying.retry(wait_fixed=2000,
                    retry_on_result=lambda r: r is False,
                    retry_on_exception=lambda _: False)
    def _wait_for_srouter_slaves_endpoints(self):
        # Get currently known agents. This request is served straight from
        # Mesos (no AdminRouter-based caching is involved).
        r = self.get('/mesos/master/slaves')
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
            r = self.get(uri)
            if r.status_code == 404:
                return False
            assert r.status_code == 200
            data = r.json()
            assert "id" in data
            assert data["id"] == slave_id

    def _wait_for_DCOS(self):
        self._wait_for_leader_election()
        self._wait_for_adminrouter_up()
        self._authenticate()
        self._wait_for_Marathon_up()
        self._wait_for_slaves_to_join()
        self._wait_for_DCOS_history_up()
        self._wait_for_srouter_slaves_endpoints()

    def _authenticate(self):
        if self.auth_enabled:
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

    def __init__(self, dcos_uri, masters, public_masters, slaves, public_slaves,
                 registry, dns_search_set, provider, auth_enabled):
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
            provider: onprem, azure, or aws
            auth_enabled: True or False
        """
        self.masters = sorted(masters)
        self.public_masters = sorted(public_masters)
        self.slaves = sorted(slaves)
        self.public_slaves = sorted(public_slaves)
        self.all_slaves = sorted(slaves+public_slaves)
        self.zk_hostports = ','.join(':'.join([host, '2181']) for host in self.public_masters)
        self.registry = registry
        self.dns_search_set = dns_search_set == 'true'
        self.provider = provider
        self.auth_enabled = auth_enabled

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
        if not disable_suauth and self.auth_enabled:
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

    def get_base_testapp_definition(self, docker_network_bridge=True, ip_per_container=False):
        """The test_server app used here is only guaranteed to exist if
        the registry_cluster pytest fixture is used
        """
        test_uuid = uuid.uuid4().hex
        base_app = {
            'id': TEST_APP_NAME_FMT.format(test_uuid),
            'container': {
                'type': 'DOCKER',
                'docker': {
                    'image': '{}/test_server'.format(self.registry),
                    'forcePullImage': True,
                },
            },
            'cmd': '/opt/test_server.py 9080',
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
        }

        if docker_network_bridge:
            base_app['container']['docker']['portMappings'] = [{
                'containerPort':  9080,
                'hostPort': 0,
                'servicePort': 0,
                'protocol': 'tcp',
            }]
            if ip_per_container:
                base_app['container']['docker']['network'] = 'USER'
                base_app['ipAddress'] = {'networkName': 'dcos'}
            else:
                base_app['container']['docker']['network'] = 'BRIDGE'
                base_app['ports'] = []
        else:
            base_app['cmd'] = '/opt/test_server.py $PORT0'
            base_app['container']['docker']['network'] = 'HOST'
            base_app['ports'] = [0]

        return base_app, test_uuid

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
        logging.info('Response from marathon: {}'.format(repr(r.json())))
        assert r.ok

        @retrying.retry(wait_fixed=1000, stop_max_delay=timeout*1000,
                        retry_on_result=lambda ret: ret is None,
                        retry_on_exception=lambda x: False)
        def _pool_for_marathon_app(app_id):
            Endpoint = collections.namedtuple("Endpoint", ["host", "port", "ip"])
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
                res = [Endpoint(t['host'], t['ports'][0], t['ipAddresses'][0]['ipAddress'])
                       for t in data['app']['tasks']]
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


@pytest.yield_fixture(scope='module')
def registry_cluster(cluster):
    """Provides a cluster that has a registry deployed via marathon.
    Note: cluster nodes must have hard-coded certs from dcos.git installed
    """
    if cluster.registry:
        return cluster
    registry_app = {
            'id': '/registry',
            'container': {
                'type': 'DOCKER',
                'docker': {
                    'image': 'mesosphere/test_registry:latest',
                    'forcePullImage': True,
                    'network': 'BRIDGE',
                    'portMappings': [{
                        'containerPort': 5000,
                        'hostPort': 0}]
                    }
                },
            "cpus": 0.1,
            "mem": 128,
            "disk": 0,
            "instances": 1,
            "healthChecks": [{
                "protocol": "COMMAND",
                "command": {
                    "value": "curl -sSfv https://registry.marathon.mesos.thisdcos.directory:$PORT0/v2/_catalog"}
                }],
            "ports": [0],
            }
    endpoints = cluster.deploy_marathon_app(registry_app)
    cluster.registry = 'registry.marathon.mesos.thisdcos.directory:'+str(endpoints[0].port)
    check_call(['sudo', 'docker', 'build', '-t', '{}/test_server'.format(cluster.registry),
                '/opt/mesosphere/active/dcos-integration-test/test_server'])
    check_call(['sudo', 'docker', 'push', '{}/test_server'.format(cluster.registry)])
    yield cluster
    cluster.destroy_marathon_app(registry_app['id'])
