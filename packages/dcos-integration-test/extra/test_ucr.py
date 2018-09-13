import uuid

__maintainer__ = 'Gilbert88'
__contact__ = 'core-team@mesosphere.io'


def test_if_ucr_app_can_be_deployed_with_image_whiteout(dcos_api_session):
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


def test_if_ucr_app_can_be_deployed_with_image_digest(dcos_api_session):
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


def test_if_ucr_app_can_be_deployed_with_auto_cgroups(dcos_api_session):
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


def test_if_ucr_pods_can_be_deployed_with_image_entrypoint(dcos_api_session):
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


def test_if_ucr_pods_can_be_deployed_with_scratch_image(dcos_api_session):
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


def test_if_ucr_pods_can_be_deployed_with_image_whiteout(dcos_api_session):
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


def test_if_ucr_pods_can_be_deployed_with_image_digest(dcos_api_session):
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


def test_if_ucr_pods_can_be_deployed_with_auto_cgroups(dcos_api_session):
    """Marathon pods inside ucr deployment integration test.

    This test launches a marathon ucr pod to verify the CPU and memory
    cgroups subsystems can be automatically loaded by the agent and the
    container specific cgroups can be correctly mounted inside the container.

    Please note that the `cgroups/all` option has been specified in the agent
    `--isolation` flag in `calculate_mesos_isolation()` which means the agent
    will automatically load all the local enabled cgroups subsystems. And the
    resources read from the container specific cgroups include both the two
    container's resources (0.2 CPU and 64MB memory) and the default executor's
    resources (0.1 CPU and 32MB memory), so in total the resources are 0.3 CPU
    (i.e., 0.3 * 1024 = 307 CPU shares) and 96MB memory (i.e., 100663296 bytes).
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
                'exec': {
                    'command': {
                        'shell': 'test `cat /sys/fs/cgroup/memory/memory.soft_limit_in_bytes` = 100663296 && '
                                 'test `cat /sys/fs/cgroup/cpu/cpu.shares` = 307'
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
