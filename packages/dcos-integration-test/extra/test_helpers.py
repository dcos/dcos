import copy
import datetime
import json
import logging
import os
import uuid

import retrying

from dcos_test_utils import marathon

__maintainer__ = 'mellenburg'
__contact__ = 'tools-infra-team@mesosphere.io'

TEST_APP_NAME_FMT = 'integration-test-{}'


def get_exhibitor_admin_password():
    try:
        with open('/opt/mesosphere/etc/exhibitor_realm', 'r') as f:
            exhibitor_realm = f.read().strip()
    except FileNotFoundError:
        # Unset. Return the default value.
        return ''

    creds = exhibitor_realm.split(':')[1].strip()
    password = creds.split(',')[0].strip()
    return password


def _get_bundle_list(dcos_api_session):
    response = check_json(dcos_api_session.health.get('/report/diagnostics/list/all'))
    bundles = []
    for _, bundle_list in response.items():
        if bundle_list is not None and isinstance(bundle_list, list) and len(bundle_list) > 0:
            # append bundles and get just the filename.
            bundles += map(lambda s: os.path.basename(s['file_name']), bundle_list)
    return bundles


def check_json(response):
    response.raise_for_status()
    try:
        json_response = response.json()
        logging.debug('Response: {}'.format(json_response))
    except ValueError:
        logging.exception('Could not deserialize response contents:{}'.format(response.content.decode()))
        raise
    assert len(json_response) > 0, 'Empty JSON returned from dcos-diagnostics request'
    return json_response


@retrying.retry(wait_fixed=2000, stop_max_delay=120000,
                retry_on_result=lambda x: x is False)
def wait_for_diagnostics_job(dcos_api_session, last_datapoint):
    response = check_json(dcos_api_session.health.get('/report/diagnostics/status/all'))
    # find if the job is still running
    job_running = False
    percent_done = 0
    for _, attributes in response.items():
        assert 'is_running' in attributes, '`is_running` field is missing in response'
        assert 'job_progress_percentage' in attributes, '`job_progress_percentage` field is missing in response'

        if attributes['is_running']:
            percent_done = attributes['job_progress_percentage']
            logging.info("Job is running. Progress: {}".format(percent_done))
            job_running = True
            break

    # if we ran this bit previously compare the current datapoint with the one we saved
    if last_datapoint['time'] and last_datapoint['value']:
        if percent_done <= last_datapoint['value']:
            assert (datetime.datetime.now() - last_datapoint['time']) < datetime.timedelta(seconds=15), (
                "Job is not progressing"
            )
    last_datapoint['value'] = percent_done
    last_datapoint['time'] = datetime.datetime.now()

    return not job_running


# sometimes it may take extra few seconds to list bundles after the job is finished.
@retrying.retry(stop_max_delay=5000)
def wait_for_diagnostics_list(dcos_api_session):
    assert _get_bundle_list(dcos_api_session), 'get a list of bundles timeout'


# make the expanded config available at import time to allow determining
# which tests should run before the test suite kicks off
with open('/opt/mesosphere/etc/expanded.config.json', 'r') as f:
    expanded_config = json.load(f)
    # expanded.config.json doesn't contain secret values, so we need to read the Exhibitor admin password from
    # Exhibitor's config.
    # TODO: Remove this hack. https://jira.mesosphere.com/browse/QUALITY-1611
    expanded_config['exhibitor_admin_password'] = get_exhibitor_admin_password()


def marathon_test_app_linux(
        host_port: int=0,
        container_port: int=None,
        container_type: marathon.Container=marathon.Container.NONE,
        network: marathon.Network=marathon.Network.HOST,
        healthcheck_protocol: marathon.Healthcheck=marathon.Healthcheck.HTTP,
        vip: str=None,
        host_constraint: str=None,
        network_name: str='dcos'):
    """ Creates an app definition for the python test server which will be
    consistent (i.e. deployable with green health checks and desired network
    routability). To learn more about the test server, see in this repo:
    ../packages/dcos-integration-test/extra/util/python_test_server.py

    Args:
        host_port: port that marathon will use to route traffic into the
            test server container. If set to zero, then marathon will assign
            a port (which is referenced by index).
        container_port: if network is BRIDGE, then the container can have a
            port remapped inside the container. In HOST or USER network, the
            container port must be the same as the host port
        container_type: can be NONE (default Mesos runtime), MESOS (the UCR),
            or DOCKER
        health_check_protocol: can be MESOS_HTTP or HTTP
        vip: either named or unnamed VIP to be applied to the host port
        host_constraint: string representing a hostname for an agent that this
            app should run on

    Return:
        (dict, str): 2-Tuple of app definition (dict) and app ID (string)
    """
    if network == marathon.Network.BRIDGE:
        if container_port is None:
            # provide a dummy value for the bridged container port if user is indifferent
            container_port = 8080
    else:
        assert container_port is None or container_port == host_port, 'Cannot declare a different host and '\
            'container port outside of BRIDGE network'
        container_port = host_port
    if network == marathon.Network.USER:
        assert host_port != 0, 'Cannot auto-assign a port on USER network!'

    test_uuid = uuid.uuid4().hex
    app = copy.deepcopy({
        'id': TEST_APP_NAME_FMT.format(test_uuid),
        'cpus': 0.1,
        'mem': 32,
        'instances': 1,
        'cmd': '/opt/mesosphere/bin/dcos-shell python '
               '/opt/mesosphere/active/dcos-integration-test/util/python_test_server.py {}'.format(
                   # If network is host and host port is zero, then the port is auto-assigned
                   # and the commandline should reference the port with the marathon built-in
                   '$PORT0' if host_port == 0 and network == marathon.Network.HOST else container_port),
        'env': {
            'DCOS_TEST_UUID': test_uuid,
            # required for python_test_server.py to run as nobody
            'HOME': '/'
        },
        'healthChecks': [
            {
                'protocol': healthcheck_protocol.value,
                'path': '/ping',
                'gracePeriodSeconds': 5,
                'intervalSeconds': 10,
                'timeoutSeconds': 10,
                'maxConsecutiveFailures': 120  # ~20 minutes until restarting
                # killing the container will rarely, if ever, help this application
                # reach a healthy state, so do not trigger a restart if unhealthy
            }
        ],
    })
    if host_port == 0:
        # port is being assigned by marathon so refer to this port by index
        app['healthChecks'][0]['portIndex'] = 0
    elif network == marathon.Network.BRIDGE:
        app['healthChecks'][0]['port'] = container_port if \
            healthcheck_protocol == marathon.Healthcheck.MESOS_HTTP else host_port
    else:
        # HOST or USER network with non-zero host port
        app['healthChecks'][0]['port'] = host_port
    if container_type != marathon.Container.NONE:
        app['container'] = {
            'type': container_type.value,
            'docker': {'image': 'debian:jessie'},
            'volumes': [{
                'containerPath': '/opt/mesosphere',
                'hostPath': '/opt/mesosphere',
                'mode': 'RO'}]}
        if container_type == marathon.Container.DOCKER:
            app['container']['docker']['network'] = network.value
            if network != marathon.Network.HOST:
                app['container']['docker']['portMappings'] = [{
                    'hostPort': host_port,
                    'containerPort': container_port,
                    'protocol': 'tcp',
                    'name': 'test'}]
                if vip is not None:
                    app['container']['docker']['portMappings'][0]['labels'] = {'VIP_0': vip}
    if network == marathon.Network.HOST:
        app['portDefinitions'] = [{
            'protocol': 'tcp',
            'port': host_port,
            'name': 'test'}]
        if vip is not None:
            app['portDefinitions'][0]['labels'] = {'VIP_0': vip}
    elif network == marathon.Network.USER:
        app['ipAddress'] = {'networkName': network_name}
        if container_type != marathon.Container.DOCKER:
            app['ipAddress']['discovery'] = {
                'ports': [{
                    'protocol': 'tcp',
                    'name': 'test',
                    'number': host_port,
                }]
            }
            if vip is not None:
                app['ipAddress']['discovery']['ports'][0]['labels'] = {'VIP_0': vip}
    elif network == marathon.Network.BRIDGE:
        if container_type == marathon.Container.MESOS:
            app['networks'] = [{'mode': 'container/bridge'}]
            app['container']['portMappings'] = [{
                'hostPort': host_port,
                'containerPort': container_port,
                'protocol': 'tcp',
                'name': 'test'}]
            if vip is not None:
                app['container']['portMappings'][0]['labels'] = {'VIP_0': vip}
    if host_constraint is not None:
        app['constraints'] = [['hostname', 'CLUSTER', host_constraint]]
    return app, test_uuid


def marathon_test_app_windows(
        host_constraint: str=None,
        host_port: int=None,
        network_name: str='dcosnat'):
    """ Creates an app definition for the python test server container

    Args:
        host_port: port that marathon will use to route traffic into the
            test server container.
        host_constraint: string representing a hostname for an agent that this
            app should run on

    Return:
        (dict, str): 2-Tuple of app definition (dict) and app ID (string)
    """
    # Container type can be only DOCKER
    container_type = marathon.Container.DOCKER
    # This will return an app definition to spawn the microsoft/iis container
    # which uses port 80
    container_port = 80
    if host_port is None:
        # provide a dummy value if user is indifferent
        host_port = 31500

    test_uuid = uuid.uuid4().hex
    app = copy.deepcopy({
        'id': TEST_APP_NAME_FMT.format(test_uuid),
        'cpus': 1,
        'mem': 512,
        'disk': 0,
        'instances': 1,
        'healthChecks': [
            {
                'protocol': 'MESOS_HTTP',
                'path': '/',
                'gracePeriodSeconds': 300,
                'intervalSeconds': 60,
                'timeoutSeconds': 20,
                'maxConsecutiveFailures': 3,
                'port': container_port,
                'path': '/',
                'ignoreHttp1xx': False
            }
        ],
    })

    app['networks'] = [
        {'mode': 'container', 'name': network_name}]
    app['container'] = {
        'type': container_type.value,
        'docker': {'image': 'microsoft/iis:windowsservercore-1803'},
        'volumes': []}
    app['container']['docker']['forcePullImage'] = False
    app['container']['docker']['privileged'] = False
    app['container']['docker']['portMappings'] = [{
        'containerPort': container_port,
        'hostPort': host_port}]

    if host_constraint is not None:
        app['constraints'] = [['hostname', 'CLUSTER', host_constraint]]
    # Add Windows constraint
    app['constraints'] = app.get('constraints', []) + [['os', 'LIKE', 'Windows']]
    app['acceptedResourceRoles'] = ["slave_public"]

    return app, test_uuid


marathon_test_app = marathon_test_app_linux
