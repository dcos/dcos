import contextlib
import logging
import uuid

import pytest

import retrying
import test_helpers

__maintainer__ = 'mnaboka'
__contact__ = 'dcos-cluster-ops@mesosphere.io'


LATENCY = 60
METRICS_WAITTIME = 5 * 60 * 1000
METRICS_INTERVAL = 2 * 1000
STD_WAITTIME = 15 * 60 * 1000
STD_INTERVAL = 5 * 1000


def test_metrics_agents_ping(dcos_api_session):
    """ Test that the metrics service is up on masters.
    """
    for agent in dcos_api_session.slaves:
        response = dcos_api_session.metrics.get('/ping', node=agent)
        assert response.status_code == 200, 'Status code: {}, Content {}'.format(response.status_code, response.content)
        assert response.json()['ok'], 'Status code: {}, Content {}'.format(response.status_code, response.content)
        'agent.'

    for agent in dcos_api_session.public_slaves:
        response = dcos_api_session.metrics.get('/ping', node=agent)
        assert response.status_code == 200, 'Status code: {}, Content {}'.format(response.status_code, response.content)
        assert response.json()['ok'], 'Status code: {}, Content {}'.format(response.status_code, response.content)


@pytest.mark.supportedwindows
def test_metrics_masters_ping(dcos_api_session):
    for master in dcos_api_session.masters:
        response = dcos_api_session.metrics.get('/ping', node=master)
        assert response.status_code == 200, 'Status code: {}, Content {}'.format(response.status_code, response.content)
        assert response.json()['ok'], 'Status code: {}, Content {}'.format(response.status_code, response.content)


@retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
def get_metrics_prom(dcos_api_session, node):
    """Gets metrics from prometheus port on node and returns the response.

    Retries on non-200 status for up to 300 seconds.

    """
    response = dcos_api_session.session.request(
        'GET', 'http://{}:61091/metrics'.format(node))
    assert response.status_code == 200, 'Status code: {}'.format(response.status_code)
    return response


def test_metrics_agents_prom(dcos_api_session):
    for agent in dcos_api_session.slaves:
        get_metrics_prom(dcos_api_session, agent)


def test_metrics_masters_prom(dcos_api_session):
    for master in dcos_api_session.masters:
        get_metrics_prom(dcos_api_session, master)


@contextlib.contextmanager
def deploy_and_cleanup_dcos_package(dcos_api_session, package_name, package_version, framework_name):
    """Deploys dcos package and waits for package teardown once the context is left"""
    app_id = dcos_api_session.cosmos.install_package(package_name, package_version=package_version).json()['appId']
    dcos_api_session.marathon.wait_for_deployments_complete()

    try:
        yield
    finally:
        dcos_api_session.cosmos.uninstall_package(package_name, app_id=app_id)

        # Retry for 15 minutes for teardown completion
        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=STD_WAITTIME)
        def wait_for_package_teardown():
            state_response = dcos_api_session.get('/state', host=dcos_api_session.masters[0], port=5050)
            assert state_response.status_code == 200
            state = state_response.json()

            for framework in state['frameworks']:
                if framework['name'] == framework_name:
                    raise Exception('Framework {} still running'.format(framework_name))
        wait_for_package_teardown()


@retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
def get_task_hostname(dcos_api_session, framework_name, task_name):
    # helper func that gets a framework's task's hostname
    mesos_id = node = ''
    state_response = dcos_api_session.get('/state', host=dcos_api_session.masters[0], port=5050)
    assert state_response.status_code == 200
    state = state_response.json()

    for framework in state['frameworks']:
        if framework['name'] == framework_name:
            for task in framework['tasks']:
                if task['name'] == task_name:
                    mesos_id = task['slave_id']
                    break
            break

    assert mesos_id is not None

    for agent in state['slaves']:
        if agent['id'] == mesos_id:
            node = agent['hostname']
            break

    return node


@pytest.mark.skipif(
    test_helpers.expanded_config.get('security') == 'strict',
    reason="MoM disabled for strict mode")
def test_task_metrics_metadata(dcos_api_session):
    """Test that task metrics have expected metadata/labels"""
    with deploy_and_cleanup_dcos_package(dcos_api_session, 'marathon', '1.6.535', 'marathon-user'):
        node = get_task_hostname(dcos_api_session, 'marathon', 'marathon-user')

        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
        def check_metrics_metadata():
            response = get_metrics_prom(dcos_api_session, node)
            for line in response.text.splitlines():
                if '#' in line:
                    continue
                if 'task_name="marathon-user"' in line:
                    assert 'service_name="marathon"' in line
                    # check for whitelisted label
                    assert 'DCOS_SERVICE_NAME="marathon-user"' in line
        check_metrics_metadata()


@pytest.mark.skipif(
    test_helpers.expanded_config.get('security') == 'strict',
    reason="Framework disabled for strict mode")
@pytest.mark.xfailflake(
    jira='DCOS_OSS-4568',
    reason='Framework hello-world still running',
    since='2018-12-14',
)
def test_executor_metrics_metadata(dcos_api_session):
    """Test that executor metrics have expected metadata/labels"""
    with deploy_and_cleanup_dcos_package(dcos_api_session, 'hello-world', '2.2.0-0.42.2', 'hello-world'):
        node = get_task_hostname(dcos_api_session, 'marathon', 'hello-world')

        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
        def check_executor_metrics_metadata():
            response = get_metrics_prom(dcos_api_session, node)
            for line in response.text.splitlines():
                if '#' in line:
                    continue
                # ignore metrics from hello-world task started by marathon by checking
                # for absence of 'marathon' string.
                if 'cpus_nr_periods' in line and 'marathon' not in line:
                    assert 'service_name="hello-world"' in line
                    assert 'task_name=""' in line  # this is an executor, not a task
                    # hello-world executors can be named "hello" or "world"
                    assert ('executor_name="hello"' in line or 'executor_name="world"' in line)
        check_executor_metrics_metadata()


def test_metrics_node(dcos_api_session):
    """Test that the '/system/v1/metrics/v0/node' endpoint returns the expected
    metrics and metric metadata.
    """
    def expected_datapoint_response(response):
        """Enure that the "node" endpoint returns a "datapoints" dict.
        """
        assert 'datapoints' in response, '"datapoints" dictionary not found'
        'in response, got {}'.format(response)

        for dp in response['datapoints']:
            assert 'name' in dp, '"name" parameter should not be empty, got {}'.format(dp)
            if 'filesystem' in dp['name']:
                assert 'tags' in dp, '"tags" key not found, got {}'.format(dp)

                assert 'path' in dp['tags'], ('"path" tag not found for filesystem metric, '
                                              'got {}'.format(dp))

                assert len(dp['tags']['path']) > 0, ('"path" tag should not be empty for '
                                                     'filesystem metrics, got {}'.format(dp))

        return True

    def expected_dimension_response(response):
        """Ensure that the "node" endpoint returns a dimensions dict that
        contains a non-empty string for cluster_id.
        """
        assert 'dimensions' in response, '"dimensions" object not found in'
        'response, got {}'.format(response)

        assert 'cluster_id' in response['dimensions'], '"cluster_id" key not'
        'found in dimensions, got {}'.format(response)

        assert response['dimensions']['cluster_id'] != "", 'expected cluster to contain a value'

        assert response['dimensions']['mesos_id'] == '', 'expected dimensions to include empty "mesos_id"'

        return True

    # Retry for 30 seconds for for the node metrics content to appear.
    @retrying.retry(stop_max_delay=30000)
    def wait_for_node_response(node):
        response = dcos_api_session.metrics.get('/node', node=node)
        assert response.status_code == 200
        return response

    # private agents
    for agent in dcos_api_session.slaves:
        response = wait_for_node_response(agent)

        assert response.status_code == 200, 'Status code: {}, Content {}'.format(
            response.status_code, response.content)
        assert expected_datapoint_response(response.json())
        assert expected_dimension_response(response.json())

    # public agents
    for agent in dcos_api_session.public_slaves:
        response = wait_for_node_response(agent)

        assert response.status_code == 200, 'Status code: {}, Content {}'.format(
            response.status_code, response.content)
        assert expected_datapoint_response(response.json())
        assert expected_dimension_response(response.json())

    # masters
    for master in dcos_api_session.masters:
        response = wait_for_node_response(master)

        assert response.status_code == 200, 'Status code: {}, Content {}'.format(
            response.status_code, response.content)
        assert expected_datapoint_response(response.json())
        assert expected_dimension_response(response.json())


@pytest.mark.xfailflake(
    jira='DCOS_OSS-4486',
    reason='test_metrics_containers fails with container metrics response status 204',
    since='2018-11-20',
)
def test_metrics_containers(dcos_api_session):
    """If there's a deployed container on the slave, iterate through them to check for
    the statsd-emitter executor. When found, query it's /app endpoint to test that
    it's sending the statsd metrics as expected.
    """
    # Helper func to check for non-unique CID's in a given /containers/id endpoint
    def check_cid(registry):
        if len(registry) <= 1:
            return True

        cid1 = registry[len(registry) - 1]
        cid2 = registry[len(registry) - 2]
        if cid1 != cid2:
            raise ValueError('{} != {}'.format(cid1, cid2))

        return True

    def check_tags(tags: dict, expected_tag_names: set):
        """Assert that tags contains only expected keys with nonempty values."""
        assert set(tags.keys()) == expected_tag_names
        for tag_name, tag_val in tags.items():
            assert tag_val != '', 'Value for tag "%s" must not be empty'.format(tag_name)

    @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=LATENCY * 1000)
    def test_containers(app_endpoints):

        debug_task_name = []

        for agent in app_endpoints:
            for c in get_container_ids(dcos_api_session, agent.host):
                # Test that /containers/<id> responds with expected data
                container_metrics = get_container_metrics(dcos_api_session, agent.host, c)

                cid_registry = []
                for dp in container_metrics['datapoints']:
                    # Verify expected tags are present.
                    assert 'tags' in dp, 'got {}'.format(dp)
                    expected_tag_names = {
                        'container_id',
                    }
                    if 'executor_name' in dp['tags']:
                        # if present we want to make sure it has a valid value.
                        expected_tag_names.add('executor_name')
                    if dp['name'].startswith('blkio.'):
                        # blkio stats have 'blkio_device' tags.
                        expected_tag_names.add('blkio_device')
                    check_tags(dp['tags'], expected_tag_names)

                    # Ensure all container ID's in the container/<id> endpoint are
                    # the same.
                    cid_registry.append(dp['tags']['container_id'])
                    assert(check_cid(cid_registry))

                assert container_metrics['dimensions']['mesos_id'] == '', 'got {}'.format(
                    container_metrics['dimensions'])

                debug_task_name.append(container_metrics['dimensions']['task_name'])

                # looking for "statsd-emitter"
                if 'statsd-emitter' == container_metrics['dimensions']['task_name']:
                    # Test that /app response is responding with expected data
                    app_metrics = get_app_metrics(dcos_api_session, agent.host, c)

                    # Ensure all /container/<id>/app data is correct
                    # We expect three datapoints, could be in any order
                    uptime_dp = None
                    for dp in app_metrics['datapoints']:
                        if dp['name'] == 'statsd_tester.time.uptime':
                            uptime_dp = dp
                            break

                    # If this metric is missing, statsd-emitter's metrics were not received
                    assert uptime_dp is not None, 'got {}'.format(app_metrics)

                    datapoint_keys = ['name', 'value', 'unit', 'timestamp', 'tags']
                    for k in datapoint_keys:
                        assert k in uptime_dp, 'got {}'.format(uptime_dp)

                    expected_tag_names = {
                        'dcos_cluster_id',
                        'test_tag_key',
                        'dcos_cluster_name',
                        'host'
                    }
                    check_tags(uptime_dp['tags'], expected_tag_names)
                    assert uptime_dp['tags']['test_tag_key'] == 'test_tag_value', 'got {}'.format(uptime_dp)

                    assert 'dimensions' in app_metrics, 'got {}'.format(app_metrics)
                    assert app_metrics['dimensions']['mesos_id'] == '', 'got {}'.format(app_metrics)

                    return True

        assert False, 'Did not find statsd-emitter container, executor IDs found: {}'.format(debug_task_name)

    marathon_config = {
        "id": "/statsd-emitter",
        "cmd": "./statsd-emitter -debug",
        "fetch": [
            {
                "uri": "https://downloads.mesosphere.com/dcos-metrics/1.11.0/statsd-emitter",
                "executable": True
            }
        ],
        "cpus": 0.5,
        "mem": 128.0,
        "instances": 1
    }
    with dcos_api_session.marathon.deploy_and_cleanup(marathon_config, check_health=False):
        endpoints = dcos_api_session.marathon.get_app_service_endpoints(marathon_config['id'])
        assert len(endpoints) == 1, 'The marathon app should have been deployed exactly once.'
        test_containers(endpoints)


def test_metrics_containers_app(dcos_api_session):
    """Assert that app metrics appear in the v0 metrics API."""
    task_name = 'test-metrics-containers-app'
    # Mixing case in the metric name allows us to ensure that metrics are
    # coerced to lowercase: https://jira.mesosphere.com/browse/DCOS-43639
    metric_name_in_pfx = 'Test_Metrics_Containers_App'
    metric_name_out_pfx = 'test_metrics_containers_app'

    marathon_app = {
        'id': '/' + task_name,
        'instances': 1,
        'cpus': 0.1,
        'mem': 128,
        'cmd': '\n'.join([
            'echo "Sending metrics to $STATSD_UDP_HOST:$STATSD_UDP_PORT"',
            'echo "Sending gauge"',
            'echo "{}.gauge:100|g" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_in_pfx),

            'echo "Sending counts"',
            'echo "{}.count:1|c" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_in_pfx),
            'echo "{}.count:1|c" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_in_pfx),

            'echo "Sending timings"',
            'echo "{}.timing:1|ms" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_in_pfx),
            'echo "{}.timing:2|ms" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_in_pfx),
            'echo "{}.timing:3|ms" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_in_pfx),

            'echo "Sending histograms"',
            'echo "{}.histogram:1|h" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_in_pfx),
            'echo "{}.histogram:2|h" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_in_pfx),
            'echo "{}.histogram:3|h" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_in_pfx),
            'echo "{}.histogram:4|h" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_in_pfx),

            'echo "Done. Sleeping forever."',
            'while true; do',
            '  sleep 1000',
            'done',
        ]),
        'container': {
            'type': 'MESOS',
            'docker': {'image': 'library/alpine'}
        },
        'networks': [{'mode': 'host'}],
    }
    expected_metrics = [
        # metric_name, metric_value
        ('.'.join([metric_name_out_pfx, 'gauge']), 100),
        ('.'.join([metric_name_out_pfx, 'count']), 2),
        ('.'.join([metric_name_out_pfx, 'timing', 'count']), 3),
        ('.'.join([metric_name_out_pfx, 'histogram', 'count']), 4),
    ]

    with dcos_api_session.marathon.deploy_and_cleanup(marathon_app, check_health=False):
        endpoints = dcos_api_session.marathon.get_app_service_endpoints(marathon_app['id'])
        assert len(endpoints) == 1, 'The marathon app should have been deployed exactly once.'
        node = endpoints[0].host
        for metric_name, metric_value in expected_metrics:
            assert_app_metric_value_for_task(dcos_api_session, node, task_name, metric_name, metric_value)


def test_metrics_containers_nan(dcos_api_session):
    """Assert that the metrics API can handle app metric gauges with NaN values."""
    task_name = 'test-metrics-containers-nan'
    metric_name = 'test_metrics_containers_nan'
    marathon_app = {
        'id': '/' + task_name,
        'instances': 1,
        'cpus': 0.1,
        'mem': 128,
        'cmd': '\n'.join([
            'echo "Sending gauge with NaN value to $STATSD_UDP_HOST:$STATSD_UDP_PORT"',
            'echo "{}:NaN|g" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name),
            'echo "Done. Sleeping forever."',
            'while true; do',
            '  sleep 1000',
            'done',
        ]),
        'container': {
            'type': 'MESOS',
            'docker': {'image': 'library/alpine'}
        },
        'networks': [{'mode': 'host'}],
    }
    with dcos_api_session.marathon.deploy_and_cleanup(marathon_app, check_health=False):
        endpoints = dcos_api_session.marathon.get_app_service_endpoints(marathon_app['id'])
        assert len(endpoints) == 1, 'The marathon app should have been deployed exactly once.'
        node = endpoints[0].host

        # NaN should be converted to empty string.
        metric_value = get_app_metric_for_task(dcos_api_session, node, task_name, metric_name)['value']
        assert metric_value == '', 'unexpected metric value: {}'.format(metric_value)


@retrying.retry(wait_fixed=METRICS_INTERVAL, stop_max_delay=METRICS_WAITTIME)
def assert_app_metric_value_for_task(dcos_api_session, node: str, task_name: str, metric_name: str, metric_value):
    """Assert the value of app metric metric_name for container task_name is metric_value.

    Retries on error, non-200 status, missing container metrics, missing app
    metric, or unexpected app metric value for up to 5 minutes.

    """
    assert get_app_metric_for_task(dcos_api_session, node, task_name, metric_name)['value'] == metric_value


@retrying.retry(wait_fixed=METRICS_INTERVAL, stop_max_delay=METRICS_WAITTIME)
def get_app_metric_for_task(dcos_api_session, node: str, task_name: str, metric_name: str):
    """Return the app metric metric_name for container task_name.

    Retries on error, non-200 status, or missing container metrics, or missing
    app metric for up to 5 minutes.

    """
    app_metrics = get_app_metrics_for_task(dcos_api_session, node, task_name)
    assert app_metrics is not None, "missing metrics for task {}".format(task_name)
    dps = [dp for dp in app_metrics['datapoints'] if dp['name'] == metric_name]
    assert len(dps) == 1, 'expected 1 datapoint for metric {}, got {}'.format(metric_name, len(dps))
    return dps[0]


@retrying.retry(
    retry_on_result=lambda result: result is None,
    wait_fixed=METRICS_INTERVAL,
    stop_max_delay=METRICS_WAITTIME)
def get_app_metrics_for_task(dcos_api_session, node: str, task_name: str):
    """Return container metrics for task_name.

    Returns None if container metrics for task_name can't be found. Retries on
    error, non-200 status, or missing container metrics for up to 5 minutes.

    """
    for cid in get_container_ids(dcos_api_session, node):
        container_metrics = get_container_metrics(dcos_api_session, node, cid)
        if container_metrics['dimensions']['task_name'] == task_name:
            return get_app_metrics(dcos_api_session, node, cid)
    return None


# Retry for two and a half minutes since the collector collects
# state every 2 minutes to propogate containers to the API
@retrying.retry(wait_fixed=METRICS_INTERVAL, stop_max_delay=METRICS_WAITTIME)
def get_container_ids(dcos_api_session, node: str):
    """Return container IDs reported by the metrics API on node.

    Retries on error, non-200 status, or empty response for up to 5 minutes.

    """
    response = dcos_api_session.metrics.get('/containers', node=node)
    assert response.status_code == 200
    container_ids = response.json()
    assert len(container_ids) > 0, 'must have at least 1 container'
    return container_ids


@retrying.retry(wait_fixed=METRICS_INTERVAL, stop_max_delay=(30 * 1000))
def get_container_metrics(dcos_api_session, node: str, container_id: str):
    """Return container_id's metrics from the metrics API on node.

    Retries on error, non-200 status, or missing response fields for up
    to 30 seconds.

    """
    response = dcos_api_session.metrics.get('/containers/' + container_id, node=node)
    assert response.status_code == 200
    container_metrics = response.json()

    assert 'datapoints' in container_metrics, (
        'container metrics must include datapoints. Got: {}'.format(container_metrics)
    )
    assert 'dimensions' in container_metrics, (
        'container metrics must include dimensions. Got: {}'.format(container_metrics)
    )
    # task_name is an important dimension for identifying metrics, but it may take some time to appear in the container
    # metrics response.
    assert 'task_name' in container_metrics['dimensions'], (
        'task_name missing in dimensions. Got: {}'.format(container_metrics['dimensions'])
    )

    return container_metrics


@retrying.retry(wait_fixed=METRICS_INTERVAL, stop_max_delay=(30 * 1000))
def get_app_metrics(dcos_api_session, node: str, container_id: str):
    """Return app metrics for container_id from the metrics API on node.

    Retries on error or non-200 status for up to 30 seconds.

    """
    resp = dcos_api_session.metrics.get('/containers/' + container_id + '/app', node=node)
    assert resp.status_code == 200, 'got {}'.format(resp.status_code)
    app_metrics = resp.json()
    assert 'datapoints' in app_metrics, 'got {}'.format(app_metrics)
    assert 'dimensions' in app_metrics, 'got {}'.format(app_metrics)
    return app_metrics


@pytest.mark.skipif(
    test_helpers.expanded_config.get('security') == 'strict',
    reason='Only resource providers are authorized to launch standalone containers in strict mode. See DCOS-42325.')
def test_standalone_container_metrics(dcos_api_session):
    """
    An operator should be able to launch a standalone container using the
    LAUNCH_CONTAINER call of the agent operator API. Additionally, if the
    process running within the standalone container emits statsd metrics, they
    should be accessible via the DC/OS metrics API.
    """
    # Fetch the mesos master state to get an agent ID
    master_ip = dcos_api_session.masters[0]
    r = dcos_api_session.get('/state', host=master_ip, port=5050)
    assert r.status_code == 200
    state = r.json()

    # Find hostname and ID of an agent
    assert len(state['slaves']) > 0, 'No agents found in master state'
    agent_hostname = state['slaves'][0]['hostname']
    agent_id = state['slaves'][0]['id']
    logging.debug('Selected agent %s at %s', agent_id, agent_hostname)

    def _post_agent(json):
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        r = dcos_api_session.post(
            '/api/v1',
            host=agent_hostname,
            port=5051,
            headers=headers,
            json=json,
            data=None,
            stream=False)
        return r

    # Prepare container ID data
    container_id = {'value': 'test-standalone-%s' % str(uuid.uuid4())}

    # Launch standalone container. The command for this container executes a
    # binary installed with DC/OS which will emit statsd metrics.
    launch_data = {
        'type': 'LAUNCH_CONTAINER',
        'launch_container': {
            'command': {
                'value': './statsd-emitter',
                'uris': [{
                    'value': 'https://downloads.mesosphere.com/dcos-metrics/1.11.0/statsd-emitter',
                    'executable': True
                }]
            },
            'container_id': container_id,
            'resources': [
                {
                    'name': 'cpus',
                    'scalar': {'value': 0.2},
                    'type': 'SCALAR'
                },
                {
                    'name': 'mem',
                    'scalar': {'value': 64.0},
                    'type': 'SCALAR'
                },
                {
                    'name': 'disk',
                    'scalar': {'value': 1024.0},
                    'type': 'SCALAR'
                }
            ],
            'container': {
                'type': 'MESOS'
            }
        }
    }

    # There is a short delay between the container starting and metrics becoming
    # available via the metrics service. Because of this, we wait up to 10
    # seconds for these metrics to appear before throwing an exception.
    def _should_retry_metrics_fetch(response):
        return response.status_code == 204

    @retrying.retry(wait_fixed=1000,
                    stop_max_delay=10000,
                    retry_on_result=_should_retry_metrics_fetch,
                    retry_on_exception=lambda x: False)
    def _get_metrics():
        master_response = dcos_api_session.get(
            '/system/v1/agent/%s/metrics/v0/containers/%s/app' % (agent_id, container_id['value']),
            host=master_ip)
        return master_response

    r = _post_agent(launch_data)
    assert r.status_code == 200, 'Received unexpected status code when launching standalone container'

    try:
        logging.debug('Successfully created standalone container with container ID %s', container_id['value'])

        # Verify that the standalone container's metrics are being collected
        r = _get_metrics()
        assert r.status_code == 200, 'Received unexpected status code when fetching standalone container metrics'

        metrics_response = r.json()
        metric_keys = [datapoint['name'] for datapoint in metrics_response['datapoints']]
        assert 'statsd_tester.time.uptime' in metric_keys
        assert metrics_response['dimensions']['container_id'] == container_id['value']
    finally:
        # Clean up the standalone container
        kill_data = {
            'type': 'KILL_CONTAINER',
            'kill_container': {
                'container_id': container_id
            }
        }

        _post_agent(kill_data)


def test_pod_application_metrics(dcos_api_session):
    """Launch a pod, wait for its containers to be added to the metrics service,
    and then verify that:
    1) Container statistics metrics are provided for the executor container
    2) Application metrics are exposed for the task container
    """
    @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=LATENCY * 1000)
    def test_application_metrics(agent_ip, agent_id, task_name, num_containers):
        # Retry for two and a half minutes since the collector collects
        # state every minute to propagate containers to the API
        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=150000)
        def wait_for_container_metrics_propagation():
            response = dcos_api_session.metrics.get('/containers', node=agent_ip)
            assert response.status_code == 200
            assert len(response.json()) == num_containers, 'Test should create {} containers'.format(num_containers)

        wait_for_container_metrics_propagation()

        get_containers = {
            "type": "GET_CONTAINERS",
            "get_containers": {
                "show_nested": True,
                "show_standalone": True
            }
        }

        r = dcos_api_session.post('/agent/{}/api/v1'.format(agent_id), json=get_containers)
        r.raise_for_status()
        mesos_agent_containers = r.json()['get_containers']['containers']

        assert len(mesos_agent_containers) == num_containers, 'Agent operator API should report '\
            'exactly {} running containers'.format(num_containers)

        def is_nested_container(container):
            """Helper to check whether or not a container returned in the
            GET_CONTAINERS response is a nested container.
            """
            return 'parent' in container['container_status']['container_id']

        def check_tags(tags: dict, expected_tag_names: set):
            """Assert that tags contain only expected keys with nonempty values."""
            assert set(tags.keys()) == expected_tag_names
            for tag_name, tag_val in tags.items():
                assert tag_val != '', 'Value for tag "%s" must not be empty'.format(tag_name)

        for container in mesos_agent_containers:
            container_id = container['container_id']['value']

            # Test that /containers/<id> responds with expected data.
            container_id_path = '/containers/{}'.format(container_id)

            if (is_nested_container(container)):
                # Retry for 30 seconds for each nested container to appear.
                # Since nested containers do not report resource statistics, we
                # expect the response code to be 204.
                @retrying.retry(stop_max_delay=30000)
                def wait_for_container_response():
                    response = dcos_api_session.metrics.get(container_id_path, node=agent_ip)
                    assert response.status_code == 204
                    return response

                # For the nested container, we do not expect any container-level
                # resource statistics, so this response should be empty.
                assert not wait_for_container_response().json()

                # Test that expected application metrics are present.
                app_response = dcos_api_session.metrics.get('/containers/{}/app'.format(container_id), node=agent_ip)
                assert app_response.status_code == 200, 'got {}'.format(app_response.status_code)

                # Ensure all /container/<id>/app data is correct
                assert 'datapoints' in app_response.json(), 'got {}'.format(app_response.json())

                # Look for the datapoint provided by the 'statsd-emitter'.
                uptime_dp = None
                for dp in app_response.json()['datapoints']:
                    if dp['name'] == 'statsd_tester.time.uptime':
                        uptime_dp = dp
                        break

                # If this metric is missing, statsd-emitter's metrics were not received.
                assert uptime_dp is not None, 'got {}'.format(app_response.json())

                datapoint_keys = ['name', 'value', 'unit', 'timestamp', 'tags']
                for k in datapoint_keys:
                    assert k in uptime_dp, 'got {}'.format(uptime_dp)

                expected_tag_names = {
                    'dcos_cluster_id',
                    'test_tag_key',
                    'dcos_cluster_name',
                    'host'
                }
                check_tags(uptime_dp['tags'], expected_tag_names)
                assert uptime_dp['tags']['test_tag_key'] == 'test_tag_value', 'got {}'.format(uptime_dp)

                assert 'dimensions' in app_response.json(), 'got {}'.format(app_response.json())
                assert 'task_name' in app_response.json()['dimensions'], 'got {}'.format(
                    app_response.json()['dimensions'])

                # Look for the specified task name.
                assert task_name.strip('/') == app_response.json()['dimensions']['task_name'],\
                    'Nested container was not tagged with the correct task name'
            else:
                # Retry for 30 seconds for each parent container to present its
                # content.
                @retrying.retry(stop_max_delay=30000)
                def wait_for_container_response():
                    response = dcos_api_session.metrics.get(container_id_path, node=agent_ip)
                    assert response.status_code == 200
                    return response

                container_response = wait_for_container_response()
                assert 'datapoints' in container_response.json(), 'got {}'.format(container_response.json())

                first_cid = None
                for dp in container_response.json()['datapoints']:
                    # Verify expected tags are present.
                    assert 'tags' in dp, 'got {}'.format(dp)
                    expected_tag_names = {
                        'container_id',
                    }
                    if dp['name'].startswith('blkio.'):
                        # blkio stats have 'blkio_device' tags.
                        expected_tag_names.add('blkio_device')
                    check_tags(dp['tags'], expected_tag_names)

                    # Ensure all container IDs in the response from the
                    # containers/<id> endpoint are the same.
                    this_cid = dp['tags']['container_id']
                    if first_cid is not None:
                        assert first_cid == this_cid, 'All container IDs in the response should be the same'
                    else:
                        first_cid = this_cid

                assert 'dimensions' in container_response.json(), 'got {}'.format(container_response.json())

                # The executor container shouldn't expose application metrics.
                app_response = dcos_api_session.metrics.get('/containers/{}/app'.format(container_id), node=agent_ip)
                assert app_response.status_code == 204, 'got {}'.format(app_response.status_code)

                return True

    marathon_pod_config = {
        "id": "/statsd-emitter-task-group",
        "containers": [{
            "name": "statsd-emitter-task",
            "resources": {
                "cpus": 0.5,
                "mem": 128.0,
                "disk": 1024.0
            },
            "image": {
                "kind": "DOCKER",
                "id": "alpine"
            },
            "exec": {
                "command": {
                    "shell": "./statsd-emitter"
                }
            },
            "artifacts": [{
                "uri": "https://downloads.mesosphere.com/dcos-metrics/1.11.0/statsd-emitter",
                "executable": True
            }],
        }],
        "scheduling": {
            "instances": 1
        }
    }

    with dcos_api_session.marathon.deploy_pod_and_cleanup(marathon_pod_config):
        r = dcos_api_session.marathon.get('/v2/pods/{}::status'.format(marathon_pod_config['id']))
        r.raise_for_status()
        data = r.json()

        assert len(data['instances']) == 1, 'The marathon pod should have been deployed exactly once.'

        test_application_metrics(
            data['instances'][0]['agentHostname'],
            data['instances'][0]['agentId'],
            marathon_pod_config['containers'][0]['name'], 2)
