import collections
import copy
import logging
import uuid
from contextlib import contextmanager
from urllib.parse import urlparse, urlunparse

import dns.exception
import dns.resolver
import requests
import retrying

TEST_APP_NAME_FMT = '/integration-test-{}'


class ClusterApi:

    adminrouter_master_port = {'http': 80, 'https': 443}
    adminrouter_agent_port = {'http': 61001, 'https': 61002}

    @retrying.retry(wait_fixed=1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _wait_for_marathon_up(self):
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
    def _wait_for_dcos_history_up(self):
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
        # only check against the slaves we expect to be in the cluster
        # so we can check that cluster has returned after a failure
        # in which case will will have new slaves and dead slaves
        slaves_ids = sorted(x['id'] for x in data['slaves'] if x['hostname'] in self.all_slaves)

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

    @retrying.retry(wait_fixed=2000,
                    retry_on_result=lambda r: r is False,
                    retry_on_exception=lambda _: False)
    def _wait_for_metronome(self):
        r = self.get('/service/metronome/v1/jobs')
        # 500 and 504 are the expected behavior of a service
        # backend that is not up and running.
        if r.status_code == 500 or r.status_code == 504:
            logging.info("Metronome gateway timeout, continue waiting for backend...")
            return False
        assert r.status_code == 200

    def wait_for_dcos(self):
        self._wait_for_leader_election()
        self._wait_for_adminrouter_up()
        if self.auth_enabled and self.web_auth_default_user:
            self._authenticate_default_user()
        self._wait_for_marathon_up()
        self._wait_for_slaves_to_join()
        self._wait_for_dcos_history_up()
        self._wait_for_srouter_slaves_endpoints()
        self._wait_for_metronome()

    @retrying.retry(wait_fixed=2000, stop_max_delay=120 * 1000)
    def _authenticate_default_user(self):
        """retry default auth user because in some deployments,
        the auth endpoint might not be routable immediately
        after adminrouter is up. DcosUser.authenticate()
        will raise exception if authorization fails
        """
        self.web_auth_default_user.authenticate(self)

    def __init__(self, dcos_uri, masters, public_masters, slaves, public_slaves,
                 dns_search_set, provider, auth_enabled, default_os_user, web_auth_default_user=None):
        """Proxy class for DC/OS clusters.

        Args:
            dcos_uri: address for the DC/OS web UI.
            masters: list of Mesos master advertised IP addresses.
            public_masters: list of Mesos master IP addresses routable from
                the local host.
            slaves: list of Mesos slave/agent advertised IP addresses.
            dns_search_set: string indicating that a DNS search domain is
                configured if its value is "true".
            provider: onprem, azure, or aws
            auth_enabled: True or False
            default_os_user: default user that marathon/metronome will launch tasks under
            web_auth_default_user: if auth_enabled, use this user's auth for all requests
                Note: user must be authenticated explicitly or call self.wait_for_dcos()
        """
        self.masters = sorted(masters)
        self.public_masters = sorted(public_masters)
        self.slaves = sorted(slaves)
        self.public_slaves = sorted(public_slaves)
        self.all_slaves = sorted(slaves + public_slaves)
        self.zk_hostports = ','.join(':'.join([host, '2181']) for host in self.public_masters)
        self.dns_search_set = dns_search_set == 'true'
        self.provider = provider
        self.auth_enabled = auth_enabled
        self.default_os_user = default_os_user
        self.web_auth_default_user = web_auth_default_user

        assert len(self.masters) == len(self.public_masters)

        # URI must include scheme
        assert dcos_uri.startswith('http')
        self.scheme = urlparse(dcos_uri).scheme

        # Make URI never end with /
        self.dcos_uri = dcos_uri.rstrip('/')

    @staticmethod
    def _marathon_req_headers():
        return {'Accept': 'application/json, text/plain, */*'}

    def _suheader(self, disable_suauth):
        if not disable_suauth and self.auth_enabled:
            return self.web_auth_default_user.auth_header
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

    def node_get(self, node, path="", params=None, disable_suauth=False, **kwargs):
        """Execute a GET request against the adminrouter on node."""
        hdrs = self._suheader(disable_suauth)
        hdrs.update(kwargs.pop('headers', {}))

        if node in self.masters:
            port = self.adminrouter_master_port[self.scheme]
        elif node in self.all_slaves:
            port = self.adminrouter_agent_port[self.scheme]
        else:
            raise Exception('Node {} is not in the cluster.'.format(node))
        url = urlunparse([self.scheme, ':'.join([node, str(port)]), path, None, None, None])
        return requests.get(url, params=params, headers=hdrs, **kwargs)

    def get_test_app(self, custom_port=False):
        test_uuid = uuid.uuid4().hex
        app = copy.deepcopy({
            'id': TEST_APP_NAME_FMT.format(test_uuid),
            'cpus': 0.1,
            'mem': 32,
            'instances': 1,
            # NOTE: uses '.' rather than `source`, since `source` only exists in bash and this is
            # run by sh
            'cmd': '. /opt/mesosphere/environment.export && /opt/mesosphere/bin/python '
                   '/opt/mesosphere/active/dcos-integration-test/python_test_server.py ',
            'env': {
                'DCOS_TEST_UUID': test_uuid
            },
            'healthChecks': [
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
        })

        if not custom_port:
            app['cmd'] += '$PORT0'
            app['portDefinitions'] = [{
                "protocol": "tcp",
                "port": 0,
                "name": "test"
            }]

        return app, test_uuid

    def get_test_app_in_docker(self, ip_per_container):
        app, test_uuid = self.get_test_app(custom_port=True)
        assert 'portDefinitions' not in app
        app['cmd'] += '9080'  # Fixed port for inside bridge networking or IP per container
        app['container'] = {
            'type': 'DOCKER',
            'docker': {
                # TODO(cmaloney): Switch to alpine with glibc
                'image': 'debian:jessie',
                'portMappings': [{
                    'hostPort': 0,
                    'containerPort': 9080,
                    'protocol': 'tcp',
                    'name': 'test',
                    'labels': {}
                }],

            },
            'volumes': [{
                'containerPath': '/opt/mesosphere',
                'hostPath': '/opt/mesosphere',
                'mode': 'RO'
            }]
        }

        if ip_per_container:
            app['container']['docker']['network'] = 'USER'
            app['ipAddress'] = {'networkName': 'dcos'}
        else:
            app['container']['docker']['network'] = 'BRIDGE'

        return app, test_uuid

    def deploy_test_app_and_check(self, app, test_uuid):
        """This method deploys the test server app and then
        pings its /operating_environment endpoint to retrieve the container
        user running the task.

        In a mesos container, this will be the marathon user
        In a docker container this user comes from the USER setting
            from the app's Dockerfile, which, for the test application
            is the default, root
        """
        if 'container' in app and app['container']['type'] == 'DOCKER':
            marathon_user = 'root'
        else:
            marathon_user = app.get('user', self.default_os_user)
        with self.marathon_deploy_and_cleanup(app) as service_points:
            r = requests.get('http://{}:{}/test_uuid'.format(service_points[0].host,
                                                             service_points[0].port))
            if r.status_code != 200:
                msg = "Test server replied with non-200 reply: '{0} {1}. "
                msg += "Detailed explanation of the problem: {2}"
                raise Exception(msg.format(r.status_code, r.reason, r.text))

            r_data = r.json()

            assert r_data['test_uuid'] == test_uuid

            # Test the app is running as root
            r = requests.get('http://{}:{}/operating_environment'.format(
                service_points[0].host,
                service_points[0].port))

            if r.status_code != 200:
                msg = "Test server replied with non-200 reply: '{0} {1}. "
                msg += "Detailed explanation of the problem: {2}"
                raise Exception(msg.format(r.status_code, r.reason, r.text))

            assert r.json() == {'username': marathon_user}

    def deploy_marathon_app(self, app_definition, timeout=120, check_health=True, ignore_failed_tasks=False):
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

        @retrying.retry(wait_fixed=1000, stop_max_delay=timeout * 1000,
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

            check_tasks_running = (data['app']['tasksRunning'] == app_definition['instances'])
            check_tasks_healthy = (not check_health or data['app']['tasksHealthy'] == app_definition['instances'])

            if (check_tasks_running and check_tasks_healthy):
                res = [Endpoint(t['host'], t['ports'][0], t['ipAddresses'][0]['ipAddress'])
                       for t in data['app']['tasks']]
                logging.info('Application deployed, running on {}'.format(res))
                return res
            elif (not check_tasks_running):
                logging.info('Waiting for application to be deployed: '
                             'Not all instances are running: {}'.format(repr(data)))
                return None
            elif (not check_tasks_healthy):
                logging.info('Waiting for application to be deployed: '
                             'Not all instances are healthy: {}'.format(repr(data)))
                return None
            else:
                logging.info('Waiting for application to be deployed: {}'.format(repr(data)))
                return None

        try:
            return _pool_for_marathon_app(app_definition['id'])
        except retrying.RetryError:
            raise Exception("Application deployment failed - operation was not "
                            "completed in {} seconds.".format(timeout))

    def destroy_marathon_app(self, app_name, timeout=120):
        """Remove a marathon app

        Abort the test if the removal was unsuccesful.

        Args:
            app_name: name of the applicatoin to remove
            timeout: seconds to wait for destruction before failing test
        """
        @retrying.retry(wait_fixed=1000, stop_max_delay=timeout * 1000,
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
            raise Exception("Application destroy failed - operation was not "
                            "completed in {} seconds.".format(timeout))

    @contextmanager
    def marathon_deploy_and_cleanup(self, app_definition, timeout=120, check_health=True, ignore_failed_tasks=False):
        yield self.deploy_marathon_app(
            app_definition, timeout, check_health, ignore_failed_tasks)
        self.destroy_marathon_app(app_definition['id'], timeout)

    def metronome_one_off(self, job_definition, timeout=300, ignore_failures=False):
        """Run a job on metronome and block until it returns success
        """
        job_id = job_definition['id']

        @retrying.retry(wait_fixed=2000, stop_max_delay=timeout * 1000,
                        retry_on_result=lambda ret: not ret,
                        retry_on_exception=lambda x: False)
        def wait_for_completion():
            r = self.get('/service/metronome/v1/jobs/' + job_id, {'embed': 'history'})
            assert r.ok
            out = r.json()
            if not ignore_failures and (out['history']['failureCount'] != 0):
                raise Exception('Metronome job failed!: ' + repr(out))
            if out['history']['successCount'] != 1:
                logging.info('Waiting for one-off to finish. Status: ' + repr(out))
                return False
            logging.info('Metronome one-off successful')
            return True
        logging.info('Creating metronome job: ' + repr(job_definition))
        r = self.post('/service/metronome/v1/jobs', job_definition)
        assert r.ok, r.json()
        logging.info('Starting metronome job')
        r = self.post('/service/metronome/v1/jobs/{}/runs'.format(job_id))
        assert r.ok, r.json()
        wait_for_completion()
        logging.info('Deleting metronome one-off')
        r = self.delete('/service/metronome/v1/jobs/' + job_id)
        assert r.ok
