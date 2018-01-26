import logging
import uuid

import pytest
import requests

import test_helpers
from dcos_test_utils import marathon

log = logging.getLogger(__name__)


def deploy_test_app_and_check(dcos_api_session, app: dict, test_uuid: str):
    """This method deploys the test server app and then
    pings its /operating_environment endpoint to retrieve the container
    user running the task.

    In a mesos container, this will be the marathon user
    In a docker container this user comes from the USER setting
    from the app's Dockerfile, which, for the test application
    is the default, root
    """
    default_os_user = 'nobody' if test_helpers.expanded_config.get('security') == 'strict' else 'root'

    if 'container' in app and app['container']['type'] == 'DOCKER':
        marathon_user = 'root'
    else:
        marathon_user = app.get('user', default_os_user)
    with dcos_api_session.marathon.deploy_and_cleanup(app):
        service_points = dcos_api_session.marathon.get_app_service_endpoints(app['id'])
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


def deploy_test_app_and_check_windows(dcos_api_session, app: dict, test_uuid: str):
    """This method deploys the IIS container and then checks
    if the container is up and can accept connections on port 80.
    """
    with dcos_api_session.marathon.deploy_and_cleanup(app):
        service_points = dcos_api_session.marathon.get_app_service_endpoints(app['id'])
        # Note: Windows will run an IIS which exposes port 80
        r = requests.get('http://{}:{}'.format(service_points[0].host, 80))
        if r.status_code != 200:
            msg = "Test server replied with non-200 reply: '{0} {1}. "
            msg += "Detailed explanation of the problem: {2}"
            raise Exception(msg.format(r.status_code, r.reason, r.text))


def test_if_marathon_app_can_be_deployed(dcos_api_session):
    """Marathon app deployment integration test

    This test verifies that marathon app can be deployed, and that service points
    returned by Marathon indeed point to the app that was deployed.

    The application being deployed is a simple http server written in python.
    Please test_server.py for more details.

    This is done by assigning an unique UUID to each app and passing it to the
    docker container as an env variable. After successful deployment, the
    "GET /test_uuid" request is issued to the app. If the returned UUID matches
    the one assigned to test - test succeeds.
    """
    deploy_test_app_and_check(dcos_api_session, *test_helpers.marathon_test_app())


def test_if_docker_app_can_be_deployed(dcos_api_session):
    """Marathon app inside docker deployment integration test.

    Verifies that a marathon app inside of a docker daemon container can be
    deployed and accessed as expected.
    """
    deploy_test_app_and_check(
        dcos_api_session,
        *test_helpers.marathon_test_app(
            network=marathon.Network.BRIDGE,
            container_type=marathon.Container.DOCKER,
            container_port=9080))


@pytest.mark.supportedwindows
@pytest.mark.supportedwindowsonly
def test_if_docker_app_can_be_deployed_windows(dcos_api_session):
    """Marathon app inside docker deployment integration test.

    Verifies that a marathon app inside of a docker daemon container can be
    deployed and accessed as expected on Windows.
    """
    deploy_test_app_and_check_windows(dcos_api_session, *test_helpers.marathon_test_app_windows())


@pytest.mark.parametrize('healthcheck', [
    marathon.Healthcheck.HTTP,
    marathon.Healthcheck.MESOS_HTTP,
])
def test_if_ucr_app_can_be_deployed(dcos_api_session, healthcheck):
    """Marathon app inside ucr deployment integration test.

    Verifies that a marathon docker app inside of a ucr container can be
    deployed and accessed as expected.
    """
    deploy_test_app_and_check(
        dcos_api_session,
        *test_helpers.marathon_test_app(
            container_type=marathon.Container.MESOS,
            healthcheck_protocol=healthcheck))


def test_if_marathon_app_can_be_deployed_with_mesos_containerizer(dcos_api_session):
    """Marathon app deployment integration test using the Mesos Containerizer

    This test verifies that a Marathon app using the Mesos containerizer with
    a Docker image can be deployed.

    This is done by assigning an unique UUID to each app and passing it to the
    docker container as an env variable. After successfull deployment, the
    "GET /test_uuid" request is issued to the app. If the returned UUID matches
    the one assigned to test - test succeds.

    When port mapping is available (MESOS-4777), this test should be updated to
    reflect that.
    """
    deploy_test_app_and_check(
        dcos_api_session,
        *test_helpers.marathon_test_app(container_type=marathon.Container.MESOS))


def test_if_marathon_pods_can_be_deployed_with_mesos_containerizer(dcos_api_session):
    """Marathon pods deployment integration test using the Mesos Containerizer

    This test verifies that a Marathon pods can be deployed.
    """

    test_uuid = uuid.uuid4().hex

    # create pod with trivial apps that function as long running processes
    pod_definition = {
        'id': '/integration-test-pods-{}'.format(test_uuid),
        'scaling': {'kind': 'fixed', 'instances': 1},
        'environment': {'PING': 'PONG'},
        'containers': [
            {
                'name': 'ct1',
                'resources': {'cpus': 0.1, 'mem': 32},
                'image': {'kind': 'DOCKER', 'id': 'debian:jessie'},
                'exec': {'command': {'shell': 'touch foo; while true; do sleep 1; done'}},
                'healthcheck': {'command': {'shell': 'test -f foo'}}
            },
            {
                'name': 'ct2',
                'resources': {'cpus': 0.1, 'mem': 32},
                'exec': {'command': {'shell': 'echo $PING > foo; while true; do sleep 1; done'}},
                'healthcheck': {'command': {'shell': 'test $PING = `cat foo`'}}
            }
        ],
        'networks': [{'mode': 'host'}]
    }

    with dcos_api_session.marathon.deploy_pod_and_cleanup(pod_definition):
        # Trivial app if it deploys, there is nothing else to check
        pass


@pytest.mark.skipif(
    test_helpers.expanded_config.get('security') == 'strict',
    reason='See: https://jira.mesosphere.com/browse/DCOS-14760')
def test_octarine(dcos_api_session, timeout=30):
    # This app binds to port 80. This is only required by the http (not srv)
    # transparent mode test. In transparent mode, we use ".mydcos.directory"
    # to go to localhost, the port attached there is only used to
    # determine which port to send traffic to on localhost. When it
    # reaches the proxy, the port is not used, and a request is made
    # to port 80.

    app, uuid = test_helpers.marathon_test_app(host_port=80)
    app['acceptedResourceRoles'] = ["slave_public"]
    app['requirePorts'] = True

    with dcos_api_session.marathon.deploy_and_cleanup(app):
        service_points = dcos_api_session.marathon.get_app_service_endpoints(app['id'])
        port_number = service_points[0].port
        # It didn't actually grab port 80 when requirePorts was unset
        assert port_number == app['portDefinitions'][0]["port"]

        app_name = app["id"].strip("/")
        port_name = app['portDefinitions'][0]["name"]
        port_protocol = app['portDefinitions'][0]["protocol"]

        srv = "_{}._{}._{}.marathon.mesos".format(port_name, app_name, port_protocol)
        addr = "{}.marathon.mesos".format(app_name)
        transparent_suffix = ".mydcos.directory"

        standard_mode = "standard"
        transparent_mode = "transparent"

        t_addr_bind = 2508
        t_srv_bind = 2509

        standard_addr = "{}:{}/ping".format(addr, port_number)
        standard_srv = "{}/ping".format(srv)
        transparent_addr = "{}{}:{}/ping".format(addr, transparent_suffix, t_addr_bind)
        transparent_srv = "{}{}:{}/ping".format(srv, transparent_suffix, t_srv_bind)

        # The uuids are different between runs so that they don't have a
        # chance of colliding. They shouldn't anyways, but just to be safe.
        octarine_runner(dcos_api_session, standard_mode, uuid + "1", standard_addr)
        octarine_runner(dcos_api_session, standard_mode, uuid + "2", standard_srv)
        octarine_runner(dcos_api_session, transparent_mode, uuid + "3", transparent_addr, bind_port=t_addr_bind)
        octarine_runner(dcos_api_session, transparent_mode, uuid + "4", transparent_srv, bind_port=t_srv_bind)


def octarine_runner(dcos_api_session, mode, uuid, uri, bind_port=None):
    log.info("Running octarine(mode={}, uuid={}, uri={}".format(mode, uuid, uri))

    octarine = "/opt/mesosphere/bin/octarine"

    bind_port_str = ""
    if bind_port is not None:
        bind_port_str = "-bindPort {}".format(bind_port)

    server_cmd = "{} -mode {} {} {}".format(octarine, mode, bind_port_str, uuid)
    log.info("Server: {}".format(server_cmd))

    proxy = ('http://127.0.0.1:$({} --client --port {})'.format(octarine, uuid))
    curl_cmd = '''"$(curl --fail --proxy {} {})"'''.format(proxy, uri)
    expected_output = '''"$(printf "{\\n    \\"pong\\": true\\n}")"'''
    check_cmd = """sh -c '[ {} = {} ]'""".format(curl_cmd, expected_output)
    log.info("Check: {}".format(check_cmd))

    app, uuid = test_helpers.marathon_test_app()
    app['requirePorts'] = True
    app['cmd'] = server_cmd
    app['healthChecks'] = [{
        "protocol": "COMMAND",
        "command": {"value": check_cmd},
        'gracePeriodSeconds': 5,
        'intervalSeconds': 10,
        'timeoutSeconds': 10,
        'maxConsecutiveFailures': 30
    }]

    with dcos_api_session.marathon.deploy_and_cleanup(app):
        pass
