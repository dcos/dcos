import uuid

import pytest
import requests


def test_if_Marathon_app_can_be_deployed(cluster):
    """Marathon app deployment integration test

    This test verifies that marathon app can be deployed, and that service points
    returned by Marathon indeed point to the app that was deployed.

    The application being deployed is a simple http server written in python.
    Please test_server.py for more details.

    This is done by assigning an unique UUID to each app and passing it to the
    docker container as an env variable. After successfull deployment, the
    "GET /test_uuid" request is issued to the app. If the returned UUID matches
    the one assigned to test - test succeds.
    """
    app_definition, test_uuid = cluster.get_base_testapp_definition()

    service_points = cluster.deploy_marathon_app(app_definition)

    r = requests.get('http://{}:{}/test_uuid'.format(service_points[0].host,
                                                     service_points[0].port))
    if r.status_code != 200:
        msg = "Test server replied with non-200 reply: '{0} {1}. "
        msg += "Detailed explanation of the problem: {2}"
        pytest.fail(msg.format(r.status_code, r.reason, r.text))

    r_data = r.json()
    assert r_data['test_uuid'] == test_uuid

    cluster.destroy_marathon_app(app_definition['id'])


def test_if_Marathon_app_can_be_deployed_with_Mesos_containerizer(cluster):
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

    test_uuid = uuid.uuid4().hex
    test_server_cmd = '/opt/mesosphere/bin/python /opt/mesosphere/active/dcos-integration-test/test_server.py'

    app_definition = {
        'id': '/integration-test-app-{}'.format(test_uuid),
        'cpus': 0.1,
        'mem': 64,
        'cmd': test_server_cmd+' $PORT0',
        'disk': 0,
        'instances': 1,
        'healthChecks': [{
            'protocol': 'HTTP',
            'path': '/ping',
            'portIndex': 0,
            'gracePeriodSeconds': 5,
            'intervalSeconds': 10,
            'timeoutSeconds': 10,
            'maxConsecutiveFailures': 3
        }],
        'env': {
            'DCOS_TEST_UUID': test_uuid,
            'PYTHONPATH': '/opt/mesosphere/lib/python3.4/site-packages'
        },
        'container': {
            'type': 'MESOS',
            'docker': {
                'image': 'python:3.4.3-slim',
                'forcePullImage': True
            },
            'volumes': [{
                'containerPath': '/opt/mesosphere',
                'hostPath': '/opt/mesosphere',
                'mode': 'RO'
            }]
        },
        'portDefinitions': [{
            'port': 0,
            'protocol': 'tcp',
            'name': 'test'
        }]
    }

    service_points = cluster.deploy_marathon_app(app_definition)

    r = requests.get('http://{}:{}/test_uuid'.format(service_points[0].host,
                                                     service_points[0].port))
    if r.status_code != 200:
        msg = "Test server replied with non-200 reply: '{0} {1}. "
        msg += "Detailed explanation of the problem: {2}"
        pytest.fail(msg.format(r.status_code, r.reason, r.text))

    r_data = r.json()
    assert r_data['test_uuid'] == test_uuid

    cluster.destroy_marathon_app(app_definition['id'])


def test_octarine_http(cluster, timeout=30):
    """
    Test if we are able to send traffic through octarine.
    """

    test_uuid = uuid.uuid4().hex
    proxy = ('"http://127.0.0.1:$(/opt/mesosphere/bin/octarine ' +
             '--client --port marathon)"')
    check_command = 'curl --fail --proxy {} marathon.mesos'.format(proxy)

    app_definition = {
        'id': '/integration-test-app-octarine-http-{}'.format(test_uuid),
        'cpus': 0.1,
        'mem': 128,
        'ports': [0],
        'cmd': '/opt/mesosphere/bin/octarine marathon',
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

    cluster.deploy_marathon_app(app_definition)


def test_octarine_srv(cluster, timeout=30):
    """
    Test resolving SRV records through octarine.
    """

    # Limit string length so we don't go past the max SRV record length
    test_uuid = uuid.uuid4().hex[:16]
    proxy = ('"http://127.0.0.1:$(/opt/mesosphere/bin/octarine ' +
             '--client --port marathon)"')
    port_name = 'pinger'
    cmd = ('/opt/mesosphere/bin/octarine marathon & ' +
           '/opt/mesosphere/bin/python -m http.server ${PORT0}')
    raw_app_id = 'integration-test-app-octarine-srv-{}'.format(test_uuid)
    check_command = ('curl --fail --proxy {} _{}._{}._tcp.marathon.mesos')
    check_command = check_command.format(proxy, port_name, raw_app_id)

    app_definition = {
        'id': '/{}'.format(raw_app_id),
        'cpus': 0.1,
        'mem': 128,
        'cmd': cmd,
        'disk': 0,
        'instances': 1,
        'portDefinitions': [
          {
            'port': 0,
            'protocol': 'tcp',
            'name': port_name,
            'labels': {}
          }
        ],
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

    cluster.deploy_marathon_app(app_definition)
