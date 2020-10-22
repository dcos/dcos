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


def test_if_marathon_app_can_be_deployed_with_nfs_csi_volume(dcos_api_session: DcosApiSession) -> None:
    """Marathon app deployment integration test using an NFS CSI volume.

    This test verifies that a Marathon app can be deployed which attaches to
    an NFS volume provided by the NFS CSI plugin. In order to accomplish this,
    we must first set up an NFS share on one agent.
    """

    # We will run an NFS server on one agent and an app on another agent to
    # verify CSI volume functionality.
    if len(dcos_api_session.slaves) < 2:
        pytest.skip("CSI Volume Tests require a minimum of two agents.")

    expanded_config = test_helpers.get_expanded_config()
    if expanded_config.get('security') == 'strict':
        pytest.skip('Cannot setup NFS server as root user with EE strict mode enabled')

    test_uuid = uuid.uuid4().hex

    hosts = dcos_api_session.slaves[0], dcos_api_session.slaves[1]

    # A helper to run a Metronome job as root to clean up the NFS share on an agent.
    # We define this here so that it can be used during error handling.
    def cleanup_nfs() -> None:
        cleanup_command = """
            sudo systemctl stop nfs-server && \
            echo '' | sudo tee /etc/exports && \
            sudo systemctl restart nfs-utils && \
            sudo exportfs -arv && \
            sudo rm -rf /var/lib/dcos-nfs-shares/test-volume-001
        """

        cleanup_job = {
            'description': 'Clean up NFS share',
            'id': 'nfs-share-cleanup-{}'.format(test_uuid),
            'run': {
                'cmd': cleanup_command,
                'cpus': 0.5,
                'mem': 256,
                'disk': 32,
                'user': 'root',
                'restart': {'policy': 'ON_FAILURE'},
                'placement': {
                    'constraints': [{
                        'attribute': '@hostname',
                        'operator': 'LIKE',
                        'value': hosts[0]
                    }]
                }
            }
        }

        dcos_api_session.metronome_one_off(cleanup_job)

    # Run a Metronome job as root to set up the NFS share on an agent.
    command = """sudo mkdir -p /var/lib/dcos-nfs-shares/test-volume-001 && \
        sudo chown -R nobody: /var/lib/dcos-nfs-shares/test-volume-001 && \
        sudo chmod 777 /var/lib/dcos-nfs-shares/test-volume-001 && \
        echo '/var/lib/dcos-nfs-shares/test-volume-001 *(rw,sync)' | sudo tee /etc/exports && \
        sudo systemctl restart nfs-utils && \
        sudo exportfs -arv && \
        sudo systemctl start nfs-server && \
        sudo systemctl enable nfs-server
    """

    setup_job = {
        'description': 'Set up NFS share',
        'id': 'nfs-share-setup-{}'.format(test_uuid),
        'run': {
            'cmd': command,
            'cpus': 0.5,
            'mem': 256,
            'disk': 32,
            'user': 'root',
            'restart': {'policy': 'ON_FAILURE'},
            'placement': {
                'constraints': [{
                    'attribute': '@hostname',
                    'operator': 'LIKE',
                    'value': hosts[0]
                }]
            }
        }
    }

    dcos_api_session.metronome_one_off(setup_job)

    # Create an app which writes to the NFS volume.
    app = {
        'id': 'csi-nfs-write-app-{}'.format(test_uuid),
        'instances': 1,
        'cpus': 0.5,
        'mem': 256,
        'cmd': 'echo some-stuff > test-volume-dir/output && sleep 999999',
        'user': 'root',
        'container': {
            'type': 'MESOS',
            'volumes': [{
                'mode': 'rw',
                'containerPath': 'test-volume-dir',
                'external': {
                    'provider': 'csi',
                    'name': 'test-volume-001',
                    'options': {
                        'pluginName': 'nfs.csi.k8s.io',
                        'capability': {
                            'accessType': 'mount',
                            'accessMode': 'MULTI_NODE_MULTI_WRITER',
                            'fsType': 'nfs'
                        },
                        'volumeContext': {
                            'server': hosts[0],
                            'share': '/var/lib/dcos-nfs-shares/test-volume-001'
                        }
                    }
                }
            }]
        },
        'constraints': [
            [
                'hostname',
                'LIKE',
                hosts[1]
            ]
        ],
        'healthChecks': [{
            'protocol': 'COMMAND',
            'command': {'value': 'test `cat test-volume-dir/output` = some-stuff'},
            'gracePeriodSeconds': 5,
            'intervalSeconds': 10,
            'timeoutSeconds': 10,
            'maxConsecutiveFailures': 3
        }]
    }

    try:
        with dcos_api_session.marathon.deploy_and_cleanup(app):
            # Trivial app if it deploys, there is nothing else to check
            pass
    except Exception as error:
        raise(error)
    finally:
        cleanup_nfs()


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
