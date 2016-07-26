import logging
import uuid

import pytest
import requests
import retrying


def test_if_Marathon_app_can_be_deployed(registry_cluster):
    """Marathon app deployment integration test

    This test verifies that marathon app can be deployed, and that service points
    returned by Marathon indeed point to the app that was deployed.

    The application being deployed is a simple http server written in python.
    Please check test/dockers/test_server for more details.

    This is done by assigning an unique UUID to each app and passing it to the
    docker container as an env variable. After successfull deployment, the
    "GET /test_uuid" request is issued to the app. If the returned UUID matches
    the one assigned to test - test succeds.
    """
    cluster = registry_cluster
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


# By default telemetry-net sends the metrics about once a minute
# Therefore, we wait up till 2 minutes and a bit before we give up
def test_if_minuteman_routes_to_vip(cluster, timeout=125):
    """Test if we are able to connect to a task with a vip using minuteman.
    """
    # Launch the app and proxy
    test_uuid = uuid.uuid4().hex

    app_definition = {
        'id': "/integration-test-app-with-minuteman-vip-%s" % test_uuid,
        'cpus': 0.1,
        'mem': 128,
        'ports': [0],
        'cmd': 'touch imok && /opt/mesosphere/bin/python -mhttp.server ${PORT0}',
        'portDefinitions': [
            {
                'port': 0,
                'protocol': 'tcp',
                'name': 'test',
                'labels': {
                    'VIP_0': '1.2.3.4:5000'
                }
            }
        ],
        'uris': [],
        'instances': 1,
        'healthChecks': [{
            'protocol': 'HTTP',
            'path': '/',
            'portIndex': 0,
            'gracePeriodSeconds': 5,
            'intervalSeconds': 10,
            'timeoutSeconds': 10,
            'maxConsecutiveFailures': 3
        }]
    }

    cluster.deploy_marathon_app(app_definition)

    proxy_definition = {
        'id': "/integration-test-proxy-to-minuteman-vip-%s" % test_uuid,
        'cpus': 0.1,
        'mem': 128,
        'ports': [0],
        'cmd': 'chmod 755 ncat && ./ncat -v --sh-exec "./ncat 1.2.3.4 5000" -l $PORT0 --keep-open',
        'uris': ['https://s3.amazonaws.com/sargun-mesosphere/ncat'],
        'instances': 1,
        'healthChecks': [{
            'protocol': 'COMMAND',
            'command': {
                'value': 'test "$(curl -o /dev/null --max-time 5 -4 -w \'%{http_code}\' -s http://localhost:${PORT0}/|cut -f1 -d" ")" == 200'  # noqa
            },
            'gracePeriodSeconds': 0,
            'intervalSeconds': 5,
            'timeoutSeconds': 20,
            'maxConsecutiveFailures': 3,
            'ignoreHttp1xx': False
        }],
    }

    service_points = cluster.deploy_marathon_app(proxy_definition)

    @retrying.retry(wait_fixed=2000,
                    stop_max_delay=timeout*1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _ensure_routable():
        r = requests.get('http://{}:{}'.format(service_points[0].host,
                                               service_points[0].port))
        assert(r.ok)
        data = r.text
        assert 'imok' in data

    _ensure_routable()


def test_ip_per_container(registry_cluster):
    """Test if we are able to connect to a task with ip-per-container mode
    """
    cluster = registry_cluster
    # Launch the test_server in ip-per-container mode

    app_definition, test_uuid = cluster.get_base_testapp_definition(ip_per_container=True)

    app_definition['constraints'] = [['hostname', 'UNIQUE']]
    if len(cluster.slaves) >= 2:
        app_definition['instances'] = 2
    else:
        logging.warning('The IP Per Container tests needs 2 (private) agents to work')
    service_points = cluster.deploy_marathon_app(app_definition, check_health=False)

    @retrying.retry(wait_fixed=5000, stop_max_delay=300*1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: False)
    def _ensure_works():
        app_port = app_definition['container']['docker']['portMappings'][0]['containerPort']
        cmd = "curl -s -f http://{}:{}/ping".format(service_points[0].ip, app_port)
        r = requests.post('http://{}:{}/run_cmd'.format(service_points[1].host, service_points[1].port), data=cmd)
        logging.info('IP Per Container Curl Response: %s', repr(r.json()))
        assert(r.json()['status'] == 0)

    _ensure_works()
    cluster.destroy_marathon_app(app_definition['id'])
