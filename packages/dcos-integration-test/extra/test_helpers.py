import copy
import json
import logging
import subprocess
import uuid

from typing import Any, Optional

import retrying

from dcos_test_utils import marathon

__maintainer__ = 'orsenthil'
__contact__ = 'tools-infra-team@mesosphere.io'

TEST_APP_NAME_FMT = 'integration-test-{}'

log = logging.getLogger(__name__)


def get_exhibitor_admin_password() -> str:
    try:
        with open('/opt/mesosphere/etc/exhibitor_realm', 'r') as f:
            exhibitor_realm = f.read().strip()
    except FileNotFoundError:
        # Unset. Return the default value.
        return ''

    creds = exhibitor_realm.split(':')[1].strip()
    password = creds.split(',')[0].strip()
    return password


def get_expanded_config() -> Any:
    # make the expanded config available at import time to allow determining
    # which tests should run before the test suite kicks off
    with open('/opt/mesosphere/etc/expanded.config.json', 'r') as f:
        expanded_config = json.load(f)
        # expanded.config.json doesn't contain secret values, so we need to read the Exhibitor admin password from
        # Exhibitor's config.
        # TODO: Remove this hack. https://jira.mesosphere.com/browse/QUALITY-1611
        expanded_config['exhibitor_admin_password'] = get_exhibitor_admin_password()
    return expanded_config


@retrying.retry(wait_fixed=60 * 1000,       # wait for 60 seconds
                retry_on_exception=lambda exc: isinstance(exc, subprocess.CalledProcessError),  # Called Process Error
                stop_max_attempt_number=3)  # retry 3 times
def docker_pull_image(image: str) -> bool:
    log.info("\n Ensure docker image availability ahead of tests.")
    try:
        subprocess.run(["sudo", "docker", "pull", image], check=True)
        return True
    except retrying.RetryError:
        return False


def marathon_test_app_linux(
        host_port: int = 0,
        container_port: Optional[int] = None,
        container_type: marathon.Container = marathon.Container.NONE,
        network: marathon.Network = marathon.Network.HOST,
        healthcheck_protocol: marathon.Healthcheck = marathon.Healthcheck.HTTP,
        vip: Optional[str] = None,
        host_constraint: Optional[str] = None,
        network_name: str = 'dcos',
        app_name_fmt: str = TEST_APP_NAME_FMT) -> tuple:
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
        app_name_fmt: format string for unique application identifier

    Return:
        (dict, str): 2-Tuple of app definition (dict) and app ID (string)
    """
    if network != marathon.Network.HOST and container_port is None:
        # provide a dummy value for the bridged container port if user is indifferent
        container_port = 8080

    test_uuid = uuid.uuid4().hex
    app = copy.deepcopy({
        'id': app_name_fmt.format(test_uuid),
        'cpus': 0.1,
        'mem': 32,
        'instances': 1,
        'cmd': '/opt/mesosphere/bin/dcos-shell python '
               '/opt/mesosphere/active/dcos-integration-test/util/python_test_server.py {}'.format(
                   # If container port is not defined, then the port is auto-assigned and
                   # the commandline should reference the port with the marathon built-in
                   '$PORT0' if container_port is None else container_port),
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
    if container_port is not None and \
            healthcheck_protocol == marathon.Healthcheck.MESOS_HTTP:
        app['healthChecks'][0]['port'] = container_port  # type: ignore
    elif host_port == 0:
        # port is being assigned by marathon so refer to this port by index
        app['healthChecks'][0]['portIndex'] = 0  # type: ignore
    else:
        # HOST or USER network with non-zero host port
        app['healthChecks'][0]['port'] = host_port  # type: ignore

    if container_type != marathon.Container.NONE:
        app['container'] = {
            'type': container_type.value,
            'docker': {'image': 'debian:stretch-slim'},
            'volumes': [{
                'containerPath': '/opt/mesosphere',
                'hostPath': '/opt/mesosphere',
                'mode': 'RO'
            }]
        }
    else:
        app['container'] = {'type': 'MESOS'}

    if host_port != 0:
        app['requirePorts'] = True
    if network == marathon.Network.HOST:
        app['portDefinitions'] = [{
            'protocol': 'tcp',
            'port': host_port,
            'name': 'test'
        }]
        if vip is not None:
            app['portDefinitions'][0]['labels'] = {'VIP_0': vip}  # type: ignore
    else:
        app['container']['portMappings'] = [{  # type: ignore
            'hostPort': host_port,
            'containerPort': container_port,
            'protocol': 'tcp',
            'name': 'test'}]
        if vip is not None:
            app['container']['portMappings'][0]['labels'] = {'VIP_0': vip}  # type: ignore
        if network == marathon.Network.USER:
            if host_port == 0:
                del app['container']['portMappings'][0]['hostPort']  # type: ignore
            app['networks'] = [{
                'mode': 'container',
                'name': network_name
            }]
        elif network == marathon.Network.BRIDGE:
            app['networks'] = [{
                'mode': 'container/bridge'
            }]

    if host_constraint is not None:
        app['constraints'] = [['hostname', 'CLUSTER', host_constraint]]
    return app, test_uuid


def marathon_test_docker_app(app_name: str, constraints: Any = None) -> tuple:
    """ Creates an app definition for the python test server container

    Args:
        app_name: a human readable name to identify the app for debugging.
        constraints: placement spec

    Return:
        (dict, str): 2-Tuple of app definition (dict) and app ID (string)
    """
    test_uuid = uuid.uuid4().hex
    app = copy.deepcopy({
        'id': "integration-test-{}-{}".format(app_name, test_uuid),
        'cpus': 0.5,
        'mem': 128,
        'disk': 0,
        'instances': 1,
        'healthChecks': [
            {
                "gracePeriodSeconds": 90,
                "ignoreHttp1xx": False,
                "intervalSeconds": 10,
                "maxConsecutiveFailures": 3,
                "portIndex": 0,
                "timeoutSeconds": 2,
                "delaySeconds": 15,
                "protocol": "HTTP",
                "path": "/",
                "ipProtocol": "IPv4"
            }
        ],
        'container': {
            'type': 'DOCKER',
            'portMappings': [{
                'containerPort': 80,
                'hostPort': 0,
                'protocol': 'tcp',
                'name': 'http'
            }],
            'docker': {
                'image': "mcr.microsoft.com/dotnet/core/samples:aspnetapp",
                'forcePullImage': False,
                'privileged': False,
            }
        },
        "networks": [
            {
                "mode": "container/bridge"
            }
        ],
        'upgradeStrategy': {
            'maximumOverCapacity': 0,
            'minimumHealthCapacity': 0
        },
    })

    # Add Windows constraint
    app['constraints'] = app.get('constraints', []) + constraints

    return app, app['id']


marathon_test_app = marathon_test_app_linux
