import uuid

import pytest

from test_util.marathon import get_test_app, get_test_app_in_docker, get_test_app_in_ucr


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
    dcos_api_session.marathon.deploy_test_app_and_check(*get_test_app_in_docker(ip_per_container=False))


@pytest.mark.parametrize("healthcheck", [
    "HTTP",
    "MESOS_HTTP",
])
def test_if_ucr_app_can_be_deployed(dcos_api_session, healthcheck):
    """Marathon app inside ucr deployment integration test.

    Verifies that a marathon docker app inside of a ucr container can be
    deployed and accessed as expected.
    """
    dcos_api_session.marathon.deploy_test_app_and_check(*get_test_app_in_ucr(healthcheck))


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
    app, test_uuid = get_test_app()
    app['container'] = {
        'type': 'MESOS',
        'docker': {
            # TODO(cmaloney): Switch to an alpine image with glibc inside.
            'image': 'debian:jessie'
        },
        'volumes': [{
            'containerPath': '/opt/mesosphere',
            'hostPath': '/opt/mesosphere',
            'mode': 'RO'
        }]
    }
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


def test_octarine_http(dcos_api_session, timeout=30):
    """
    Test if we are able to send traffic through octarine.
    """

    test_uuid = uuid.uuid4().hex
    octarine_id = uuid.uuid4().hex
    proxy = ('"http://127.0.0.1:$(/opt/mesosphere/bin/octarine ' +
             '--client --port {})"'.format(octarine_id))
    check_command = 'curl --fail --proxy {} marathon.mesos.mydcos.directory'.format(proxy)

    app_definition = {
        'id': '/integration-test-app-octarine-http-{}'.format(test_uuid),
        'cpus': 0.1,
        'mem': 128,
        'ports': [0],
        'cmd': '/opt/mesosphere/bin/octarine {}'.format(octarine_id),
        'disk': 0,
        'instances': 1,
        'healthChecks': [{
            'protocol': 'COMMAND',
            'command': {
                'value': check_command
            },
            'gracePeriodSeconds': 5,
            'intervalSeconds': 10,
            'timeoutSeconds': 10,
            'maxConsecutiveFailures': 3
        }]
    }

    with dcos_api_session.marathon.deploy_and_cleanup(app_definition):
        pass


def test_octarine_srv(dcos_api_session, timeout=30):
    """
    Test resolving SRV records through octarine.
    """

    # Limit string length so we don't go past the max SRV record length
    test_uuid = uuid.uuid4().hex[:16]
    octarine_id = uuid.uuid4().hex
    proxy = ('"http://127.0.0.1:$(/opt/mesosphere/bin/octarine ' +
             '--client --port {})"'.format(octarine_id))
    port_name = 'pinger'
    cmd = ('/opt/mesosphere/bin/octarine {} & '.format(octarine_id) +
           '/opt/mesosphere/bin/python -m http.server ${PORT0}')
    raw_app_id = 'integration-test-app-octarine-srv-{}'.format(test_uuid)
    check_command = 'curl --fail --proxy {} _{}._{}._tcp.marathon.mesos.mydcos.directory'.format(
        proxy,
        port_name,
        raw_app_id)

    app_definition = {
        'id': '/{}'.format(raw_app_id),
        'cpus': 0.1,
        'mem': 128,
        'cmd': cmd,
        'disk': 0,
        'instances': 1,
        'portDefinitions': [{
            'port': 0,
            'protocol': 'tcp',
            'name': port_name,
            'labels': {}
        }],
        'healthChecks': [{
            'protocol': 'COMMAND',
            'command': {
                'value': check_command
            },
            'gracePeriodSeconds': 5,
            'intervalSeconds': 10,
            'timeoutSeconds': 10,
            'maxConsecutiveFailures': 3
        }]
    }

    with dcos_api_session.marathon.deploy_and_cleanup(app_definition):
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
