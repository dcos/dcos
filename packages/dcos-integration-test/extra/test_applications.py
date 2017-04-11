import logging
import uuid

import pytest

from test_util.marathon import get_test_app

log = logging.getLogger(__name__)


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
    dcos_api_session.marathon.deploy_test_app_and_check(*get_test_app())


def test_if_docker_app_can_be_deployed(dcos_api_session):
    """Marathon app inside docker deployment integration test.

    Verifies that a marathon app inside of a docker daemon container can be
    deployed and accessed as expected.
    """
    dcos_api_session.marathon.deploy_test_app_and_check(
        *get_test_app(network='BRIDGE', container_type='DOCKER', container_port=9080))


@pytest.mark.parametrize("healthcheck", [
    "HTTP",
    "MESOS_HTTP",
])
def test_if_ucr_app_can_be_deployed(dcos_api_session, healthcheck):
    """Marathon app inside ucr deployment integration test.

    Verifies that a marathon docker app inside of a ucr container can be
    deployed and accessed as expected.
    """
    dcos_api_session.marathon.deploy_test_app_and_check(
        *get_test_app(container_type='MESOS', healthcheck_protocol=healthcheck))


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
    app, test_uuid = get_test_app(container_type='MESOS')
    dcos_api_session.marathon.deploy_test_app_and_check(app, test_uuid)


def test_if_marathon_pods_can_be_deployed_with_mesos_containerizer(dcos_api_session):
    """Marathon pods deployment integration test using the Mesos Containerizer

    This test verifies that a Marathon pods can be deployed.
    """

    test_uuid = uuid.uuid4().hex

    pod_definition = {
        'id': '/integration-test-pods-{}'.format(test_uuid),
        'scaling': {'kind': 'fixed', 'instances': 1},
        'environment': {'PING': 'PONG'},
        'containers': [
            {
                'name': 'ct1',
                'resources': {'cpus': 0.1, 'mem': 32},
                'image': {'kind': 'DOCKER', 'id': 'debian:jessie'},
                'exec': {'command': {'shell': 'touch foo'}},
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


def test_octarine(dcos_api_session, timeout=30):
    # This app binds to port 80. This is only required by the http (not srv)
    # transparent mode test. In transparent mode, we use ".mydcos.directory"
    # to go to localhost, the port attached there is only used to
    # determine which port to send traffic to on localhost. When it
    # reaches the proxy, the port is not used, and a request is made
    # to port 80.

    app, uuid = get_test_app(host_port=80)
    app['acceptedResourceRoles'] = ["slave_public"]
    app['requirePorts'] = True

    with dcos_api_session.marathon.deploy_and_cleanup(app) as service_points:
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

    app, uuid = get_test_app()
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


def test_pkgpanda_api(dcos_api_session):

    def get_and_validate_package_ids(path, node):
        r = dcos_api_session.get(path, node=node)
        assert r.status_code == 200
        package_ids = r.json()
        assert isinstance(package_ids, list)
        for package_id in package_ids:
            r = dcos_api_session.get(path + package_id, node=node)
            assert r.status_code == 200
            name, version = package_id.split('--')
            assert r.json() == {'id': package_id, 'name': name, 'version': version}
        return package_ids

    active_buildinfo = dcos_api_session.get('/pkgpanda/active.buildinfo.full.json').json()
    active_buildinfo_packages = sorted(
        # Setup packages don't have a buildinfo.
        (package_name, info['package_version'] if info else None)
        for package_name, info in active_buildinfo.items()
    )

    def assert_packages_match_active_buildinfo(package_ids):
        packages = sorted(map(lambda id_: tuple(id_.split('--')), package_ids))
        assert len(packages) == len(active_buildinfo_packages)
        for package, buildinfo_package in zip(packages, active_buildinfo_packages):
            if buildinfo_package[1] is None:
                # No buildinfo for this package, so we can only compare names.
                assert package[0] == buildinfo_package[0]
            else:
                assert package == buildinfo_package

    for node in dcos_api_session.masters + dcos_api_session.all_slaves:
        package_ids = get_and_validate_package_ids('pkgpanda/repository/', node)
        active_package_ids = get_and_validate_package_ids('pkgpanda/active/', node)

        assert set(active_package_ids) <= set(package_ids)
        assert_packages_match_active_buildinfo(active_package_ids)
