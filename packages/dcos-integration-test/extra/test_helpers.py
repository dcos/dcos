import copy
import json
import sys
import uuid

from dcos_test_utils import marathon

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
        network_name: str='nat_network'):
    """ Creates an app definition for the microsoft/iis container

    Args:
        host_constraint: string representing a hostname for an agent that this
            app should run on

    Return:
        (dict, str): 2-Tuple of app definition (dict) and app ID (string)
    """
    # `BRIDGE` mode will be translated to `NAT` on Windows.
    network = "BRIDGE"
    # Container type can be only DOCKER
    container_type = marathon.Container.DOCKER

    test_uuid = uuid.uuid4().hex
    app = copy.deepcopy({
        'id': TEST_APP_NAME_FMT.format(test_uuid),
        'cpus': 1,
        'mem': 512,
        'disk': 0,
        'instances': 1,
        'cmd': None,
        'healthChecks': [
            {
                'protocol': 'HTTP',
                'path': '/',
                'gracePeriodSeconds': 300,
                'intervalSeconds': 60,
                'timeoutSeconds': 20,
                'maxConsecutiveFailures': 3,
                'port': 80,
                'ignoreHttp1xx': False
            }
        ],
    })

    app['container'] = {
        'type': container_type.value,
        'docker': {'image': 'microsoft/iis:windowsservercore-1709'},
        'volumes': []}
    app['container']['docker']['parameters'] = [
        {'key': 'network', 'value': network_name},
        {'key': 'publish', 'value': '80:80'}]
    app['container']['docker']['forcePullImage'] = False
    app['container']['docker']['network'] = network

    if host_constraint is not None:
        app['constraints'] = [['hostname', 'CLUSTER', host_constraint]]
    # Add Windows constraint
    app['constraints'] = app.get('constraints', []) + [['os', 'LIKE', 'Windows']]
    app['acceptedResourceRoles'] = ["slave_public"]

    return app, test_uuid


marathon_test_app = marathon_test_app_linux
