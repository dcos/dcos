import collections
import copy
import logging
import uuid
from contextlib import contextmanager

import requests
import retrying

import test_util.helpers

DEFAULT_API_BASE = 'marathon'
TEST_APP_NAME_FMT = '/integration-test-{}'
REQUIRED_HEADERS = {'Accept': 'application/json, text/plain, */*'}


def get_test_app(custom_port=False):
    test_uuid = uuid.uuid4().hex
    app = copy.deepcopy({
        'id': TEST_APP_NAME_FMT.format(test_uuid),
        'cpus': 0.1,
        'mem': 32,
        'instances': 1,
        'cmd': '/opt/mesosphere/bin/dcos-shell python '
               '/opt/mesosphere/active/dcos-integration-test/util/python_test_server.py ',
        'env': {
            'DCOS_TEST_UUID': test_uuid,
            # required for python_test_server.py to run as nobody
            'HOME': '/'
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


def get_test_app_in_docker(ip_per_container):
    app, test_uuid = get_test_app(custom_port=True)
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
            }]},
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


class Marathon(test_util.helpers.ApiClient):
    def __init__(self, default_host_url, default_os_user='root', api_base=DEFAULT_API_BASE,
                 default_headers=None, ca_cert_path=None):
        if default_headers is None:
            default_headers = dict()
        default_headers.update(REQUIRED_HEADERS)
        super().__init__(
            default_host_url=default_host_url,
            api_base=api_base,
            default_headers=default_headers,
            ca_cert_path=ca_cert_path)
        self.default_os_user = default_os_user

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
        with self.deploy_and_cleanup(app) as service_points:
            r = requests.get('http://{}:{}/test_uuid'.format(service_points[0].host,
                                                             service_points[0].port))
            if r.status_code != 200:
                msg = "Test server replied with non-200 reply: '{0} {1}. "
                msg += "Detailed explanation of the problem: {2}"
                raise Exception(msg.format(r.status_code, r.reason, r.text))

            r_data = r.json()

            assert r_data['test_uuid'] == test_uuid

            r = requests.get('http://{}:{}/operating_environment'.format(
                service_points[0].host,
                service_points[0].port))

            if r.status_code != 200:
                msg = "Test server replied with non-200 reply: '{0} {1}. "
                msg += "Detailed explanation of the problem: {2}"
                raise Exception(msg.format(r.status_code, r.reason, r.text))

            assert r.json() == {'username': marathon_user}

    def deploy_app(self, app_definition, timeout=120, check_health=True, ignore_failed_tasks=False):
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
        r = self.post('v2/apps', json=app_definition)
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

            r = self.get('v2/apps' + app_id, params=req_params)
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
                       if len(t['ports']) is not 0
                       else Endpoint(t['host'], 0, t['ipAddresses'][0]['ipAddress'])
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


    def deploy_test_pod_and_check(self, pod, test_uuid):
        with self.deploy_pod_and_cleanup(pod) as instances:
            assert pod['scaling']['instances'] == instances


    def deploy_pod(self, pod_definition, timeout=120):
        """Deploy a pod to marathon

        This function deploys an a pod and then waits for marathon to
        aknowledge it's successfull creation or fails the test.

        It waits until all the instances reach tasksRunning and then tasksHealthy state.

        Args:
            pod_definition: a dict with pod definition as specified in
                            Marathon API
            timeout: a time to wait for the pod to reach 'Healthy' status
                     after which the test should be failed.
            check_health: wait until Marathon reports tasks as healthy before
                          returning
        Returns:
            Scaling instance count
        """
        r = self.post('/pods', json=pod_definition)
        logging.info('Response from marathon: {}'.format(repr(r.json())))
        assert r.ok

        @retrying.retry(wait_fixed=1000, stop_max_delay=timeout * 1000,
                        retry_on_result=lambda ret: ret is False,
                        retry_on_exception=lambda x: False)
        def _wait_for_pod_deployment(pod_id):
            r = self.get('/deployments')
            data = r.json()
            if len(data) > 0:
                logging.info('Waiting for pod to be deployed %s', repr(data))
                return False
            # deployment complete
            r = self.get('/pods' + pod_id)
            data = r.json()
            return data["scaling"]["instances"]

        try:
            return _wait_for_pod_deployment(pod_definition['id'])
        except retrying.RetryError:
            raise Exception("Pod deployment failed - operation was not "
                            "completed in {} seconds.".format(timeout))


    def destroy_pod(self, pod_id, timeout=120):
        """Remove a marathon pod

        Abort the test if the removal was unsuccesful.

        Args:
            pod_id: id of the pod to remove
            timeout: seconds to wait for destruction before failing test
        """
        @retrying.retry(wait_fixed=1000, stop_max_delay=timeout * 1000,
                        retry_on_result=lambda ret: not ret,
                        retry_on_exception=lambda x: False)
        def _destroy_pod_complete(deployment_id):
            r = self.get('/deployments')
            assert r.ok

            for deployment in r.json():
                if deployment_id == deployment.get('id'):
                    logging.info('Waiting for pod to be destroyed')
                    return False
            logging.info('Pod destroyed')
            return True

        r = self.delete('/pods' + pod_id)
        assert r.ok

        try:
            _destroy_pod_complete(r.headers['Marathon-Deployment-Id'])
        except retrying.RetryError:
            raise Exception("Pod destroy failed - operation was not "
                            "completed in {} seconds.".format(timeout))


    def destroy_app(self, app_name, timeout=120):
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
            r = self.get('v2/deployments')
            assert r.ok

            for deployment in r.json():
                if deployment_id == deployment.get('id'):
                    logging.info('Waiting for application to be destroyed')
                    return False
            logging.info('Application destroyed')
            return True

        r = self.delete('v2/apps' + app_name)
        assert r.ok

        try:
            _destroy_complete(r.json()['deploymentId'])
        except retrying.RetryError:
            raise Exception("Application destroy failed - operation was not "
                            "completed in {} seconds.".format(timeout))


    @contextmanager
    def deploy_and_cleanup(self, app_definition, timeout=120, check_health=True, ignore_failed_tasks=False):
        yield self.deploy_app(
            app_definition, timeout, check_health, ignore_failed_tasks)
        self.destroy_app(app_definition['id'], timeout)


    @contextmanager
    def deploy_pod_and_cleanup(self, pod_definition, timeout=120):
        yield self.deploy_pod(pod_definition, timeout)
        self.destroy_pod(pod_definition['id'], timeout)
