import collections
import copy
import logging
import uuid
from contextlib import contextmanager

import requests
import retrying

from test_util.helpers import ApiClientSession, path_join

TEST_APP_NAME_FMT = 'integration-test-{}'
REQUIRED_HEADERS = {'Accept': 'application/json, text/plain, */*'}
log = logging.getLogger(__name__)


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
                'protocol': 'MESOS_HTTP',
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


def get_test_app_in_docker(ip_per_container=False):
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


def get_test_app_in_ucr(healthcheck='HTTP'):
    app, test_uuid = get_test_app(custom_port=True)
    assert 'portDefinitions' not in app
    # UCR does NOT support portmappings host only.  must use $PORT0
    app['cmd'] += '$PORT0'
    app['container'] = {
        'type': 'MESOS',
        'docker': {
            'image': 'debian:jessie'
        },
        'volumes': [{
            'containerPath': '/opt/mesosphere',
            'hostPath': '/opt/mesosphere',
            'mode': 'RO'
        }]
    }
    # currently UCR does NOT support bridge mode or port mappings
    # UCR supports host mode
    app['healthChecks'][0]['protocol'] = healthcheck
    return app, test_uuid


class Marathon(ApiClientSession):
    def __init__(self, default_url, default_os_user='root', session=None):
        super().__init__(default_url)
        if session is not None:
            self.session = session
        self.session.headers.update(REQUIRED_HEADERS)
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
            r = requests.get('http://{}:{}/test_uuid'.format(service_points[0].host, service_points[0].port))
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

            json_uid = r.json()['uid']
            if marathon_user == 'root':
                assert json_uid == 0, "App running as root should have uid 0."
            else:
                assert json_uid != 0, ("App running as {} should not have uid 0.".format(marathon_user))

    def deploy_app(self, app_definition, timeout=120, check_health=True, ignore_failed_tasks=False):
        """Deploy an app to marathon

        This function deploys an an application and then waits for marathon to
        acknowledge it's successful creation or fails the test.

        The wait for application is immediately aborted if Marathon returns
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
        log.info('Response from marathon: {}'.format(repr(r.json())))
        r.raise_for_status()

        @retrying.retry(wait_fixed=1000, stop_max_delay=timeout * 1000,
                        retry_on_result=lambda ret: ret is None,
                        retry_on_exception=lambda x: False)
        def _poll_marathon_for_app_deployment(app_id):
            Endpoint = collections.namedtuple("Endpoint", ["host", "port", "ip"])
            # Some of the counters need to be explicitly enabled now and/or in
            # future versions of Marathon:
            req_params = (('embed', 'apps.lastTaskFailure'),
                          ('embed', 'apps.counts'))

            r = self.get(path_join('v2/apps', app_id), params=req_params)
            r.raise_for_status()

            data = r.json()

            if not ignore_failed_tasks:
                assert 'lastTaskFailure' not in data['app'], (
                    'Application deployment failed, reason: {}'.format(data['app']['lastTaskFailure']['message'])
                )

            check_tasks_running = (data['app']['tasksRunning'] == app_definition['instances'])
            check_tasks_healthy = (not check_health or data['app']['tasksHealthy'] == app_definition['instances'])

            if check_tasks_running and check_tasks_healthy:
                res = [Endpoint(t['host'], t['ports'][0], t['ipAddresses'][0]['ipAddress'])
                       if len(t['ports']) is not 0
                       else Endpoint(t['host'], 0, t['ipAddresses'][0]['ipAddress'])
                       for t in data['app']['tasks']]
                log.info('Application deployed, running on {}'.format(res))
                return res
            elif not check_tasks_running:
                log.info('Waiting for application to be deployed: '
                         'Not all instances are running: {}'.format(repr(data)))
                return None
            elif not check_tasks_healthy:
                log.info('Waiting for application to be deployed: '
                         'Not all instances are healthy: {}'.format(repr(data)))
                return None
            else:
                log.info('Waiting for application to be deployed: {}'.format(repr(data)))
                return None

        try:
            return _poll_marathon_for_app_deployment(app_definition['id'])
        except retrying.RetryError:
            raise Exception("Application deployment failed - operation was not "
                            "completed in {} seconds.".format(timeout))

    def ensure_deployments_complete(self, timeout=120):
        """
        This method ensures that, there are no pending deployments

        :return: True if all deployments are completed within time out. Raises an exception otherwise.
        """

        @retrying.retry(wait_fixed=1000, stop_max_delay=120 * 1000, retry_on_exception=lambda x: False)
        def _get_deployments_json():
            r = self.get('v2/deployments')
            r.raise_for_status()
            return r.json()

        def retry_on_assertion_error(exception):
            return isinstance(exception, AssertionError)

        @retrying.retry(retry_on_exception=retry_on_assertion_error,
                        stop_max_attempt_number=10,
                        wait_fixed=timeout * 1000)
        def ensure_deployment_is_finished():
            deployments_json = _get_deployments_json()
            assert not deployments_json, "No deployment should be happening."

        try:
            ensure_deployment_is_finished()
        except retrying.RetryError:
            raise Exception("Deployments were not completed within {timeout} seconds".format(timeout=timeout))

    def deploy_pod(self, pod_definition, timeout=300):
        """Deploy a pod to marathon

        This function deploys an a pod and then waits for marathon to
        acknowledge it's successful creation or fails the test.

        It waits until all the instances reach tasksRunning and then tasksHealthy state.

        Args:
            pod_definition: a dict with pod definition as specified in
                            Marathon API
            timeout: seconds to wait for deployment to finish
        Returns:
            Pod data JSON
        """
        r = self.post('v2/pods', json=pod_definition)
        assert r.ok, 'status_code: {} content: {}'.format(r.status_code, r.content)
        log.info('Response from marathon: {}'.format(repr(r.json())))

        @retrying.retry(wait_fixed=2000, stop_max_delay=timeout * 1000,
                        retry_on_result=lambda ret: ret is False,
                        retry_on_exception=lambda x: False)
        def _wait_for_pod_deployment(pod_id):
            # TODO(greggomann): Revisit this logic. Can we make a request for
            # info on only our specific deployment? See DCOS-11707.
            r = self.get('v2/deployments')
            data = r.json()
            if len(data) > 0:
                log.info('Waiting for pod to be deployed %r', data)
                return False
            # deployment complete
            r = self.get('v2/pods' + pod_id)
            r.raise_for_status()
            data = r.json()
            if int(data['scaling']['instances']) != pod_definition['scaling']['instances']:
                log.info('Pod is still scaling. Continuing to wait...')
                return False
            return data
        try:
            return _wait_for_pod_deployment(pod_definition['id'])
        except retrying.RetryError as ex:
            raise Exception("Pod deployment failed - operation was not "
                            "completed in {} seconds.".format(timeout)) from ex

    def destroy_pod(self, pod_id, timeout=120):
        """Remove a marathon pod

        Abort the test if the removal was unsuccessful.

        Args:
            pod_id: id of the pod to remove
            timeout: seconds to wait for destruction before failing test
        """
        @retrying.retry(wait_fixed=1000, stop_max_delay=timeout * 1000,
                        retry_on_result=lambda ret: not ret,
                        retry_on_exception=lambda x: False)
        def _destroy_pod_complete(deployment_id):
            r = self.get('v2/deployments')
            assert r.ok, 'status_code: {} content: {}'.format(r.status_code, r.content)

            for deployment in r.json():
                if deployment_id == deployment.get('id'):
                    log.info('Waiting for pod to be destroyed')
                    return False
            log.info('Pod destroyed')
            return True

        r = self.delete('v2/pods' + pod_id)
        assert r.ok, 'status_code: {} content: {}'.format(r.status_code, r.content)

        try:
            _destroy_pod_complete(r.headers['Marathon-Deployment-Id'])
        except retrying.RetryError as ex:
            raise Exception("Pod destroy failed - operation was not "
                            "completed in {} seconds.".format(timeout)) from ex

    def destroy_app(self, app_name, timeout=120):
        """Remove a marathon app

        Abort the test if the removal was unsuccessful.

        Args:
            app_name: name of the application to remove
            timeout: seconds to wait for destruction before failing test
        """
        @retrying.retry(wait_fixed=1000, stop_max_delay=timeout * 1000,
                        retry_on_result=lambda ret: not ret,
                        retry_on_exception=lambda x: False)
        def _destroy_complete(deployment_id):
            r = self.get('v2/deployments')
            r.raise_for_status()

            for deployment in r.json():
                if deployment_id == deployment.get('id'):
                    log.info('Waiting for application to be destroyed')
                    return False
            log.info('Application destroyed')
            return True

        r = self.delete(path_join('v2/apps', app_name))
        r.raise_for_status()

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
    def deploy_pod_and_cleanup(self, pod_definition, timeout=300):
        yield self.deploy_pod(pod_definition, timeout=timeout)
        self.destroy_pod(pod_definition['id'], timeout)
