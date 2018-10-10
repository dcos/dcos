import pytest
import retrying

__maintainer__ = 'mnaboka'
__contact__ = 'dcos-cluster-ops@mesosphere.io'


LATENCY = 60


@pytest.mark.supportedwindows
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


@pytest.mark.parametrize("prometheus_port", [61091, 61092])
def test_metrics_agents_prom(dcos_api_session, prometheus_port):
    for agent in dcos_api_session.slaves:
        response = dcos_api_session.session.request('GET', 'http://' + agent + ':{}/metrics'.format(prometheus_port))
        assert response.status_code == 200, 'Status code: {}'.format(response.status_code)


@pytest.mark.supportedwindows
@pytest.mark.parametrize("prometheus_port", [61091, 61092])
def test_metrics_masters_prom(dcos_api_session, prometheus_port):
    for master in dcos_api_session.masters:
        response = dcos_api_session.session.request('GET', 'http://' + master + ':{}/metrics'.format(prometheus_port))
        assert response.status_code == 200, 'Status code: {}'.format(response.status_code)


@pytest.mark.parametrize("prometheus_port", [61091])
def test_metrics_agents_mesos(dcos_api_session, prometheus_port):
    """Assert that mesos metrics on agents are present."""
    for agent in dcos_api_session.slaves:
        response = dcos_api_session.session.request('GET', 'http://' + agent + ':{}/metrics'.format(prometheus_port))
        assert 'mesos_slave_uptime_secs' in response.text


@pytest.mark.parametrize("prometheus_port", [61091])
def test_metrics_masters_mesos(dcos_api_session, prometheus_port):
    """Assert that mesos metrics on masters are present."""
    for master in dcos_api_session.masters:
        response = dcos_api_session.session.request('GET', 'http://' + master + ':{}/metrics'.format(prometheus_port))
        assert 'mesos_master_uptime_secs' in response.text


@pytest.mark.supportedwindows
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

    @retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY * 1000)
    def test_containers(app_endpoints):

        debug_task_name = []

        for agent in app_endpoints:
            for c in get_container_ids(dcos_api_session, agent.host):
                # Test that /containers/<id> responds with expected data
                container_metrics = get_container_metrics(dcos_api_session, agent.host, c)
                assert 'datapoints' in container_metrics, 'got {}'.format(container_metrics)

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

                assert 'dimensions' in container_metrics, 'got {}'.format(container_metrics)
                assert 'task_name' in container_metrics['dimensions'], 'got {}'.format(
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

                    return True

        assert False, 'Did not find statsd-emitter container, executor IDs found: {}'.format(debug_task_name)

    marathon_config = {
        "id": "/statsd-emitter",
        "cmd": "/opt/mesosphere/bin/./statsd-emitter -debug",
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
    metric_name_pfx = 'test_metrics_containers_app'
    marathon_app = {
        'id': '/' + task_name,
        'instances': 1,
        'cpus': 0.1,
        'mem': 128,
        'cmd': '\n'.join([
            'echo "Sending metrics to $STATSD_UDP_HOST:$STATSD_UDP_PORT"',
            'echo "Sending gauge"',
            'echo "{}.gauge:100|g" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_pfx),

            'echo "Sending counts"',
            'echo "{}.count:1|c" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_pfx),
            'echo "{}.count:1|c" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_pfx),

            'echo "Sending timings"',
            'echo "{}.timing:1|ms" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_pfx),
            'echo "{}.timing:2|ms" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_pfx),
            'echo "{}.timing:3|ms" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_pfx),

            'echo "Sending histograms"',
            'echo "{}.histogram:1|h" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_pfx),
            'echo "{}.histogram:2|h" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_pfx),
            'echo "{}.histogram:3|h" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_pfx),
            'echo "{}.histogram:4|h" | nc -w 1 -u $STATSD_UDP_HOST $STATSD_UDP_PORT'.format(metric_name_pfx),

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
        ('.'.join([metric_name_pfx, 'gauge']), 100),
        ('.'.join([metric_name_pfx, 'count']), 2),
        ('.'.join([metric_name_pfx, 'timing', 'count']), 3),
        ('.'.join([metric_name_pfx, 'histogram', 'count']), 4),
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


@retrying.retry(wait_fixed=(2 * 1000), stop_max_delay=(150 * 1000))
def assert_app_metric_value_for_task(dcos_api_session, node: str, task_name: str, metric_name: str, metric_value):
    """Assert the value of app metric metric_name for container task_name is metric_value.

    Retries on error, non-200 status, missing container metrics, missing app
    metric, or unexpected app metric value for up to 150 seconds.

    """
    assert get_app_metric_for_task(dcos_api_session, node, task_name, metric_name)['value'] == metric_value


@retrying.retry(wait_fixed=(2 * 1000), stop_max_delay=(150 * 1000))
def get_app_metric_for_task(dcos_api_session, node: str, task_name: str, metric_name: str):
    """Return the app metric metric_name for container task_name.

    Retries on error, non-200 status, or missing container metrics, or missing
    app metric for up to 150 seconds.

    """
    app_metrics = get_app_metrics_for_task(dcos_api_session, node, task_name)
    assert app_metrics is not None, "missing metrics for task {}".format(task_name)
    dps = [dp for dp in app_metrics['datapoints'] if dp['name'] == metric_name]
    assert len(dps) == 1, 'expected 1 datapoint for metric {}, got {}'.format(metric_name, len(dps))
    return dps[0]


@retrying.retry(retry_on_result=lambda result: result is None, wait_fixed=(2 * 1000), stop_max_delay=(150 * 1000))
def get_app_metrics_for_task(dcos_api_session, node: str, task_name: str):
    """Return container metrics for task_name.

    Returns None if container metrics for task_name can't be found. Retries on
    error, non-200 status, or missing container metrics for up to 150 seconds.

    """
    for cid in get_container_ids(dcos_api_session, node):
        container_metrics = get_container_metrics(dcos_api_session, node, cid)
        if container_metrics['dimensions'].get('task_name') == task_name:
            return get_app_metrics(dcos_api_session, node, cid)
    return None


# Retry for two and a half minutes since the collector collects
# state every 2 minutes to propogate containers to the API
@retrying.retry(wait_fixed=(2 * 1000), stop_max_delay=(150 * 1000))
def get_container_ids(dcos_api_session, node: str):
    """Return container IDs reported by the metrics API on node.

    Retries on error, non-200 status, or empty response for up to 150 seconds.

    """
    response = dcos_api_session.metrics.get('/containers', node=node)
    assert response.status_code == 200
    container_ids = response.json()
    assert len(container_ids) > 0, 'must have at least 1 container'
    return container_ids


@retrying.retry(stop_max_delay=(30 * 1000))
def get_container_metrics(dcos_api_session, node: str, container_id: str):
    """Return container_id's metrics from the metrics API on node.

    Retries on error or non-200 status for up to 30 seconds.

    """
    response = dcos_api_session.metrics.get('/containers/' + container_id, node=node)
    assert response.status_code == 200
    return response.json()


@retrying.retry(stop_max_delay=(30 * 1000))
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
