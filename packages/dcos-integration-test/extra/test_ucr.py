import uuid

from dcos_test_utils.marathon import get_test_app


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
    app, test_uuid = get_test_app()
    app['container'] = {
        'type': 'MESOS',
        'docker': {
            'image': 'mesosphere/whiteout:test'
        }
    }
    app['cmd'] = 'while true; do sleep 1; done'
    app['healthChecks'] = [{
        'protocol': 'COMMAND',
        'command': {'value': 'test ! -f /dir1/file1 && test ! -f /dir1/dir2/file2 && test -f /dir1/dir2/file3'},
        'gracePeriodSeconds': 5,
        'intervalSeconds': 10,
        'timeoutSeconds': 10,
        'maxConsecutiveFailures': 3,
    }]
    with dcos_api_session.marathon.deploy_and_cleanup(app):
        # Trivial app if it deploys, there is nothing else to check
        pass


def test_if_ucr_app_can_be_deployed_with_image_digest(dcos_api_session):
    """Marathon app deployment integration test using the Mesos Containerizer.

    This test verifies that a marathon ucr app can execute a docker image
    by digest.
    """
    app, test_uuid = get_test_app()
    app['container'] = {
        'type': 'MESOS',
        'docker': {
            'image': 'library/alpine@sha256:9f08005dff552038f0ad2f46b8e65ff3d25641747d3912e3ea8da6785046561a'
        }
    }
    app['cmd'] = 'while true; do sleep 1; done'
    app['healthChecks'] = [{
        'protocol': 'COMMAND',
        'command': {'value': 'test -d $MESOS_SANDBOX'},
        'gracePeriodSeconds': 5,
        'intervalSeconds': 10,
        'timeoutSeconds': 10,
        'maxConsecutiveFailures': 3,
    }]
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
