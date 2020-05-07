import logging
import uuid

from typing import Any

import pytest
import requests

import test_helpers
from dcos_test_utils import marathon
from dcos_test_utils.dcos_api import DcosApiSession

__maintainer__ = 'kensipe'
__contact__ = 'orchestration-team@mesosphere.io'

log = logging.getLogger(__name__)


def deploy_test_app_and_check(dcos_api_session: DcosApiSession, app: dict, test_uuid: str) -> None:
    """This method deploys the test server app and then
    pings its /operating_environment endpoint to retrieve the container
    user running the task.

    In a mesos container, this will be the marathon user
    In a docker container this user comes from the USER setting
    from the app's Dockerfile, which, for the test application
    is the default, root
    """
    expanded_config = test_helpers.get_expanded_config()
    default_os_user = 'nobody' if expanded_config.get('security') == 'strict' else 'root'

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


@pytest.mark.first
def test_docker_image_availablity() -> None:
    assert test_helpers.docker_pull_image("debian:stretch-slim"), "docker pull failed for image used in the test"


def test_if_marathon_app_can_be_deployed(dcos_api_session: DcosApiSession) -> None:
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


def test_if_docker_app_can_be_deployed(dcos_api_session: DcosApiSession) -> None:
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


@pytest.mark.parametrize('healthcheck', [
    marathon.Healthcheck.HTTP,
    marathon.Healthcheck.MESOS_HTTP,
])
def test_if_ucr_app_can_be_deployed(dcos_api_session: DcosApiSession, healthcheck: Any) -> None:
    """Marathon app inside ucr deployment integration test.

    Verifies that a marathon docker app inside of a ucr container can be
    deployed and accessed as expected.
    """
    deploy_test_app_and_check(
        dcos_api_session,
        *test_helpers.marathon_test_app(
            container_type=marathon.Container.MESOS,
            healthcheck_protocol=healthcheck))


def test_if_marathon_app_can_be_deployed_with_mesos_containerizer(dcos_api_session: DcosApiSession) -> None:
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


def test_if_marathon_pods_can_be_deployed_with_mesos_containerizer(dcos_api_session: DcosApiSession) -> None:
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
                'image': {'kind': 'DOCKER', 'id': 'debian:stretch-slim'},
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
