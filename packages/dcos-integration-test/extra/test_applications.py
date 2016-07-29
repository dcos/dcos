import logging
import uuid

import pytest
import requests
import retrying


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


def ensure_routable(cmd, service_points, timeout=125):
    @retrying.retry(wait_fixed=2000,
                    stop_max_delay=timeout*1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: True)
    def _ensure_routable():
        proxy_uri = 'http://{}:{}/run_cmd'.format(service_points[0].host, service_points[0].port)
        logging.info('Sending {} data: {}'.format(proxy_uri, cmd))
        r = requests.post(proxy_uri, data=cmd)
        logging.info('Requests Response: %s', repr(r.json()))
        assert(r.json()['status'] == 0)
    return _ensure_routable


def test_if_minuteman_routes_to_vip(cluster):
    """Test if we are able to connect to a task with a vip using minuteman.
    """

    origin_app, origin_uuid = cluster.get_base_testapp_definition()
    origin_app['container']['docker']['portMappings'][0]['labels']['VIP_0'] = '1.2.3.4:5000'
    cluster.deploy_marathon_app(origin_app)

    proxy_app, proxy_uuid = cluster.get_base_testapp_definition()
    service_points = cluster.deploy_marathon_app(proxy_app)

    cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://1.2.3.4:5000/ping'
    ensure_routable(cmd, service_points)()

    cluster.destroy_marathon_app(origin_app['id'])
    cluster.destroy_marathon_app(proxy_app['id'])


def test_if_minuteman_routes_to_named_vip(cluster):
    """Test if we are able to connect to a task with a named vip using minuteman.
    """

    origin_app, origin_uuid = cluster.get_base_testapp_definition()
    origin_app['container']['docker']['portMappings'][0]['labels']['VIP_0'] = 'foo:5000'
    cluster.deploy_marathon_app(origin_app)

    proxy_app, proxy_uuid = cluster.get_base_testapp_definition()
    service_points = cluster.deploy_marathon_app(proxy_app)

    cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://foo.marathon.l4lb.thisdcos.directory:5000/ping'
    ensure_routable(cmd, service_points)()

    cluster.destroy_marathon_app(origin_app['id'])
    cluster.destroy_marathon_app(proxy_app['id'])


def test_ip_per_container(cluster):
    """Test if we are able to connect to a task with ip-per-container mode
    """
    # Launch the test_server in ip-per-container mode

    app_definition, test_uuid = cluster.get_base_testapp_definition(ip_per_container=True)

    app_definition['instances'] = 2
    if len(cluster.slaves) >= 2:
        app_definition['constraints'] = [['hostname', 'UNIQUE']]
    else:
        logging.warning('The IP Per Container tests needs 2 (private) agents to work')
    service_points = cluster.deploy_marathon_app(app_definition, check_health=False)
    app_port = app_definition['container']['docker']['portMappings'][0]['containerPort']
    cmd = '/opt/mesosphere/bin/curl -s -f http://{}:{}/ping'.format(service_points[1].ip, app_port)
    ensure_routable(cmd, service_points)()
    cluster.destroy_marathon_app(app_definition['id'])
