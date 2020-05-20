import uuid

import pytest
from dcos_test_utils.dcos_api import DcosApiSession

__maintainer__ = 'Gilbert88'
__contact__ = 'core-team@mesosphere.io'


def test_if_ucr_app_can_be_deployed_with_image_whiteout(dcos_api_session: DcosApiSession) -> None:
    """Marathon app deployment integration test using the Mesos Containerizer.

    This test verifies that a marathon ucr app can execute a docker image
    with whiteout files. Whiteouts are files with a special meaning for
    the layered filesystem. For more details, please see:
    https://github.com/docker/docker/blob/master/pkg/archive/whiteouts.go

    Please note that the image 'mesosphere/whiteout:test' is built on top
    of 'alpine' which is used for UCR whiteout support testing. See:
    https://hub.docker.com/r/mesosphere/whiteout/
    """
    app = {
        'id': '/test-ucr-' + str(uuid.uuid4().hex),
        'cpus': 0.1,
        'mem': 32,
        'instances': 1,
        'cmd': 'while true; do sleep 1; done',
        'container': {
            'type': 'MESOS',
            'docker': {'image': 'mesosphere/whiteout:test'}
        },
        'healthChecks': [{
            'protocol': 'COMMAND',
            'command': {'value': 'test ! -f /dir1/file1 && test ! -f /dir1/dir2/file2 && test -f /dir1/dir2/file3'},
            'gracePeriodSeconds': 5,
            'intervalSeconds': 10,
            'timeoutSeconds': 10,
            'maxConsecutiveFailures': 3
        }]
    }
    with dcos_api_session.marathon.deploy_and_cleanup(app):
        # Trivial app if it deploys, there is nothing else to check
        pass


def test_if_ucr_app_can_be_deployed_with_image_digest(dcos_api_session: DcosApiSession) -> None:
    """Marathon app deployment integration test using the Mesos Containerizer.

    This test verifies that a marathon ucr app can execute a docker image
    by digest.
    """
    app = {
        'id': '/test-ucr-' + str(uuid.uuid4().hex),
        'cpus': 0.1,
        'mem': 32,
        'instances': 1,
        'cmd': 'while true; do sleep 1; done',
        'container': {
            'type': 'MESOS',
            'docker': {
                'image': 'library/alpine@sha256:9f08005dff552038f0ad2f46b8e65ff3d25641747d3912e3ea8da6785046561a'
            }
        },
        'healthChecks': [{
            'protocol': 'COMMAND',
            'command': {'value': 'test -d $MESOS_SANDBOX'},
            'gracePeriodSeconds': 5,
            'intervalSeconds': 10,
            'timeoutSeconds': 10,
            'maxConsecutiveFailures': 3
        }]
    }
    with dcos_api_session.marathon.deploy_and_cleanup(app):
        # Trivial app if it deploys, there is nothing else to check
        pass


def test_if_ucr_app_can_be_deployed_with_auto_cgroups(dcos_api_session: DcosApiSession) -> None:
    """Marathon app deployment integration test using the Mesos Containerizer.

    This test launches a marathon ucr app to verify the CPU and memory
    cgroups subsystems can be automatically loaded by the agent and the
    container specific cgroups can be correctly mounted inside the container.

    Please note that the `cgroups/all` option has been specified in the agent
    `--isolation` flag in `calculate_mesos_isolation()` which means the agent
    will automatically load all the local enabled cgroups subsystems. And the
    resources read from the container specific cgroups include both the task's
    resources (0.1 CPU and 32MB memory) and the command executor's resources (
    0.1 CPU and 32MB memory), so in total the resources are 0.2 CPU (i.e.,
    0.2 * 1024 = 204 CPU shares) and 64MB memory (i.e., 67108864 bytes).
    """
    app = {
        'id': '/test-ucr-' + str(uuid.uuid4().hex),
        'cpus': 0.1,
        'mem': 32,
        'instances': 1,
        'cmd': 'while true; do sleep 1; done',
        'container': {
            'type': 'MESOS',
            'docker': {
                'image': 'library/alpine'
            }
        },
        'healthChecks': [{
            'protocol': 'COMMAND',
            'command': {
                'value': 'test `cat /sys/fs/cgroup/memory/memory.soft_limit_in_bytes` = 67108864 && '
                         'test `cat /sys/fs/cgroup/cpu/cpu.shares` = 204'
            },
            'gracePeriodSeconds': 5,
            'intervalSeconds': 10,
            'timeoutSeconds': 10,
            'maxConsecutiveFailures': 3
        }]
    }
    with dcos_api_session.marathon.deploy_and_cleanup(app):
        # Trivial app if it deploys, there is nothing else to check
        pass


def test_if_ucr_app_can_be_deployed_with_shm_in_specified_size(dcos_api_session: DcosApiSession) -> None:
    """Marathon app deployment integration test using the Mesos Containerizer.

    This test verifies that a marathon ucr app can be launched with a specified
    size (1234MB) of private /dev/shm.
    """
    app = {
        'id': '/test-ucr-' + str(uuid.uuid4().hex),
        'cpus': 0.1,
        'mem': 32,
        'instances': 1,
        'cmd': 'while true; do sleep 1; done',
        'container': {
            'type': 'MESOS',
            'docker': {
                'image': 'library/alpine'
            },
            "linuxInfo": {"ipcInfo": {"mode": "PRIVATE", "shmSize": 1234}}
        },
        'healthChecks': [{
            'protocol': 'COMMAND',
            'command': {'value': 'df -m /dev/shm | grep -w 1234'},
            'gracePeriodSeconds': 5,
            'intervalSeconds': 10,
            'timeoutSeconds': 10,
            'maxConsecutiveFailures': 3
        }]
    }
    with dcos_api_session.marathon.deploy_and_cleanup(app):
        # Trivial app if it deploys, there is nothing else to check
        pass


def test_if_ucr_pods_can_be_deployed_with_image_entrypoint(dcos_api_session: DcosApiSession) -> None:
    """Marathon pods inside ucr deployment integration test.

    This test verifies that a marathon ucr pod can execute a docker image
    default entrypoint.
    """
    test_uuid = uuid.uuid4().hex
    pod_definition = {
        'id': '/integration-test-pods-{}'.format(test_uuid),
        'scaling': {'kind': 'fixed', 'instances': 1},
        'environment': {'PING': 'PONG'},
        'containers': [
            {
                'name': 'container1',
                'resources': {'cpus': 0.1, 'mem': 32},
                'image': {'kind': 'DOCKER', 'id': 'mesosphere/inky'}
            },
            {
                'name': 'container2',
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


def test_if_ucr_pods_can_be_deployed_with_scratch_image(dcos_api_session: DcosApiSession) -> None:
    """Marathon pods inside ucr deployment integration test.

    This test verifies that a marathon ucr pod can execute a docker scratch
    image. A scratch image means an image that only contains a single binary
    and its dependencies.
    """
    test_uuid = uuid.uuid4().hex
    pod_definition = {
        'id': '/integration-test-pods-{}'.format(test_uuid),
        'scaling': {'kind': 'fixed', 'instances': 1},
        'environment': {'PING': 'PONG'},
        'containers': [
            {
                'name': 'container1',
                'resources': {'cpus': 0.1, 'mem': 32},
                'image': {'kind': 'DOCKER', 'id': 'hello-world'}
            },
            {
                'name': 'container2',
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


def test_if_ucr_pods_can_be_deployed_with_image_whiteout(dcos_api_session: DcosApiSession) -> None:
    """Marathon pods inside ucr deployment integration test.

    This test verifies that a marathon ucr pod can execute a docker image
    with whiteout files. Whiteouts are files with a special meaning for
    the layered filesystem. For more details, please see:
    https://github.com/docker/docker/blob/master/pkg/archive/whiteouts.go

    Please note that the image 'mesosphere/whiteout:test' is built on top
    of 'alpine' which is used for UCR whiteout support testing. See:
    https://hub.docker.com/r/mesosphere/whiteout/
    """
    test_uuid = uuid.uuid4().hex
    pod_definition = {
        'id': '/integration-test-pods-{}'.format(test_uuid),
        'scaling': {'kind': 'fixed', 'instances': 1},
        'environment': {'PING': 'PONG'},
        'containers': [
            {
                'name': 'container1',
                'resources': {'cpus': 0.1, 'mem': 32},
                'image': {'kind': 'DOCKER', 'id': 'mesosphere/whiteout:test'},
                'exec': {
                    'command': {
                        'shell': 'test ! -f /dir1/file1 && test ! -f /dir1/dir2/file2 && test -f /dir1/dir2/file3'
                    }
                }
            },
            {
                'name': 'container2',
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


def test_if_ucr_pods_can_be_deployed_with_image_digest(dcos_api_session: DcosApiSession) -> None:
    """Marathon pods inside ucr deployment integration test.

    This test verifies that a marathon ucr pod can execute a docker image
    by digest.
    """
    test_uuid = uuid.uuid4().hex
    pod_definition = {
        'id': '/integration-test-pods-{}'.format(test_uuid),
        'scaling': {'kind': 'fixed', 'instances': 1},
        'environment': {'PING': 'PONG'},
        'containers': [
            {
                'name': 'container1',
                'resources': {'cpus': 0.1, 'mem': 32},
                'image': {
                    'kind': 'DOCKER',
                    'id': 'library/alpine@sha256:9f08005dff552038f0ad2f46b8e65ff3d25641747d3912e3ea8da6785046561a'
                },
                'exec': {'command': {'shell': 'ls -al /'}}
            },
            {
                'name': 'container2',
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


def test_if_ucr_pods_can_be_deployed_with_auto_cgroups(dcos_api_session: DcosApiSession) -> None:
    """Marathon pods inside ucr deployment integration test.

    This test launches a marathon ucr pod to verify the CPU and memory
    cgroups subsystems can be automatically loaded by the agent and the
    container specific cgroups can be correctly mounted inside the container.

    Please note that the `cgroups/all` option has been specified in the agent
    `--isolation` flag in `calculate_mesos_isolation()` which means the agent
    will automatically load all the local enabled cgroups subsystems. And by
    default each container in a pod will have its own cgroups created where
    its resources will be enforced, so for the `container1` launched by this
    test, the resources read from its cgroups are 64MB memory (i.e., 67108864
    bytes) and 0.2 CPU (i.e., 0.2 * 1024 = 204 CPU shares).
    """
    test_uuid = uuid.uuid4().hex
    pod_definition = {
        'id': '/integration-test-pods-{}'.format(test_uuid),
        'scaling': {'kind': 'fixed', 'instances': 1},
        'environment': {'PING': 'PONG'},
        'containers': [
            {
                'name': 'container1',
                'resources': {'cpus': 0.2, 'mem': 64},
                'image': {'kind': 'DOCKER', 'id': 'library/alpine'},
                'exec': {
                    'command': {
                        'shell': 'test `cat /sys/fs/cgroup/memory/memory.soft_limit_in_bytes` = 67108864 && '
                                 'test `cat /sys/fs/cgroup/cpu/cpu.shares` = 204'
                    }
                }
            },
            {
                'name': 'container2',
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


# TODO: Unmute this test once volume gid manager is enabled.
@pytest.mark.skip(reason="cannot test this without volume gid manager enabled")
def test_if_ucr_pods_can_be_deployed_with_non_root_user_ephemeral_volume(dcos_api_session: DcosApiSession) -> None:
    """Marathon pods inside ucr deployment integration test.

    This test launches a marathon ucr pod with a non-root user (nobody)
    and an ephemeral volume, and verifies the container in the pod can
    write to the ephemeral volume. In strict mode, the parent container
    (i.e., the default executor) is launched as nobody as well, so the
    nested container has the permission to write to the volume since it
    is launched with nobody in this test. In permissive mode, the user
    of the parent container and the nested container are different (root
    and nobody), in this case the volume gid manager in Mesos agent will
    set the volume owner group to a unique gid and the nested container
    will be launched with that gid as its supplementary group so that it
    has the permission to write to the volume.
    """
    test_uuid = uuid.uuid4().hex
    pod_definition = {
        'id': '/integration-test-pods-{}'.format(test_uuid),
        'scaling': {'kind': 'fixed', 'instances': 1},
        'environment': {'PING': 'PONG'},
        'containers': [
            {
                'name': 'container1',
                'resources': {'cpus': 0.1, 'mem': 32},
                'image': {'kind': 'DOCKER', 'id': 'library/alpine'},
                'exec': {'command': {'shell': 'echo data > ./etc/file'}},
                'user': 'nobody',
                "volumeMounts": [{"name": "volume1", "mountPath": "etc"}]
            },
            {
                'name': 'container2',
                'resources': {'cpus': 0.1, 'mem': 32},
                'exec': {'command': {'shell': 'echo $PING > foo; while true; do sleep 1; done'}},
                'healthcheck': {'command': {'shell': 'test $PING = `cat foo`'}}
            }
        ],
        'networks': [{'mode': 'host'}],
        'volumes': [{'name': 'volume1'}]
    }
    with dcos_api_session.marathon.deploy_pod_and_cleanup(pod_definition):
        # Trivial app if it deploys, there is nothing else to check
        pass


def test_if_ucr_pods_can_share_shm_with_childs(dcos_api_session: DcosApiSession) -> None:
    """Marathon pods inside ucr deployment integration test.

    This test launches a marathon ucr pod with a specified size (1234MB)
    of private /dev/shm and share it with one of its child containers but
    not the other one, and then verifies the size of one child container's
    /dev/shm is 1234MB and the other's is not.
    """
    test_uuid = uuid.uuid4().hex
    pod_definition = {
        'id': '/integration-test-pods-{}'.format(test_uuid),
        'scaling': {'kind': 'fixed', 'instances': 1},
        'environment': {'PING': 'PONG'},
        'containers': [
            {
                'name': 'container1',
                'resources': {'cpus': 0.1, 'mem': 32},
                'image': {'kind': 'DOCKER', 'id': 'library/alpine'},
                'exec': {'command': {'shell': 'df -m /dev/shm | grep -w 1234'}},
                'linuxInfo': {'ipcInfo': {'mode': 'SHARE_PARENT'}}
            },
            {
                'name': 'container2',
                'resources': {'cpus': 0.1, 'mem': 32},
                'exec': {
                    'command': {
                        'shell': 'test -z $(df -m /dev/shm | grep -w 1234) && '
                                 'echo $PING > foo; while true; do sleep 1; done'
                    }
                },
                'healthcheck': {'command': {'shell': 'test $PING = `cat foo`'}}
            }
        ],
        'networks': [{'mode': 'host'}],
        'linuxInfo': {'ipcInfo': {'mode': 'PRIVATE', 'shmSize': 1234}}
    }
    with dcos_api_session.marathon.deploy_pod_and_cleanup(pod_definition):
        # Trivial app if it deploys, there is nothing else to check
        pass
