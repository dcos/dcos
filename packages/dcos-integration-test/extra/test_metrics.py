import common
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


def test_metrics_agents_prom(dcos_api_session):
    for agent in dcos_api_session.slaves:
        response = dcos_api_session.session.request('GET', 'http://' + agent + ':61091/metrics')
        assert response.status_code == 200, 'Status code: {}'.format(response.status_code)


def test_metrics_masters_prom(dcos_api_session):
    for master in dcos_api_session.masters:
        response = dcos_api_session.session.request('GET', 'http://' + master + ':61091/metrics')
        assert response.status_code == 200, 'Status code: {}'.format(response.status_code)


@retrying.retry(wait_fixed=2000, stop_max_delay=150 * 1000)
def get_metrics_prom(dcos_api_session, node, expected_metrics):
    """Assert that expected metrics are present on prometheus port on node.

    Retries on non-200 status or missing expected metrics
    for up to 150 seconds.

    """
    response = dcos_api_session.session.request('GET', 'http://{}:61091/metrics'.format(node))
    assert response.status_code == 200, 'Status code: {}'.format(response.status_code)
    for metric_name in expected_metrics:
        assert metric_name in response.text


def test_metrics_agents_mesos(dcos_api_session):
    """Assert that mesos metrics on agents are present."""
    for agent in dcos_api_session.slaves:
        get_metrics_prom(dcos_api_session, agent, ['mesos_slave_uptime_secs'])


def test_metrics_masters_mesos(dcos_api_session):
    """Assert that mesos metrics on masters are present."""
    for master in dcos_api_session.masters:
        get_metrics_prom(dcos_api_session, master, ['mesos_master_uptime_secs'])


def test_metrics_masters_zookeeper(dcos_api_session):
    """Assert that ZooKeeper metrics on masters are present."""
    for master in dcos_api_session.masters:
        get_metrics_prom(dcos_api_session, master, ['ZooKeeper', 'zookeeper_avg_latency'])


def test_metrics_agents_statsd(dcos_api_session):
    """Assert that statsd metrics on agent are present."""
    if len(dcos_api_session.slaves) > 0:
        agent = dcos_api_session.slaves[0]
        task_name = 'test-metrics-statsd-app'
        metric_name_pfx = 'test_metrics_statsd_app'
        marathon_app = {
            'id': '/' + task_name,
            'instances': 1,
            'cpus': 0.1,
            'mem': 128,
            'env': {
                'STATIC_STATSD_UDP_PORT': '61825',
                'STATIC_STATSD_UDP_HOST': 'localhost'
            },
            'cmd': '\n'.join([
                'echo "Sending metrics to $STATIC_STATSD_UDP_HOST:$STATIC_STATSD_UDP_PORT"',
                'echo "Sending gauge"',
                'echo "{}.gauge:100|g" | nc -w 1 -u $STATIC_STATSD_UDP_HOST $STATIC_STATSD_UDP_PORT'.format(
                    metric_name_pfx),

                'echo "Sending counts"',
                'echo "{}.count:1|c" | nc -w 1 -u $STATIC_STATSD_UDP_HOST $STATIC_STATSD_UDP_PORT'.format(
                    metric_name_pfx),

                'echo "Sending timings"',
                'echo "{}.timing:1|ms" | nc -w 1 -u $STATIC_STATSD_UDP_HOST $STATIC_STATSD_UDP_PORT'.format(
                    metric_name_pfx),

                'echo "Sending histograms"',
                'echo "{}.histogram:1|h" | nc -w 1 -u $STATIC_STATSD_UDP_HOST $STATIC_STATSD_UDP_PORT'.format(
                    metric_name_pfx),

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
            'constraints': [['hostname', 'LIKE', agent]],
        }
        expected_metrics = [
            ('TYPE ' + '_'.join([metric_name_pfx, 'gauge']) + ' gauge'),
            ('TYPE ' + '_'.join([metric_name_pfx, 'count']) + ' counter'),
            ('TYPE ' + '_'.join([metric_name_pfx, 'timing', 'count']) + ' untyped'),
            ('TYPE ' + '_'.join([metric_name_pfx, 'histogram', 'count']) + ' untyped'),
        ]

        with dcos_api_session.marathon.deploy_and_cleanup(marathon_app, check_health=False):
            endpoints = dcos_api_session.marathon.get_app_service_endpoints(marathon_app['id'])
            assert len(endpoints) == 1, 'The marathon app should have been deployed exactly once.'
            get_metrics_prom(dcos_api_session, agent, expected_metrics)


@retrying.retry(wait_fixed=2000, stop_max_delay=300 * 1000)
def check_metrics_prom(dcos_api_session, node, check_func):
    """Get metrics from prometheus port on node and run check_func function,
    asserting that it returns True.

    Retries on non-200 status or failed assertions
    for up to 300 seconds.

    """
    response = dcos_api_session.session.request(
        'GET', 'http://{}:61091/metrics'.format(node))
    assert response.status_code == 200, 'Status code: {}'.format(response.status_code)
    assert check_func(response) is True


def test_metrics_metadata(dcos_api_session):
    # get count of all running containers to check against later for complete teardown of kafka
    num_containers = 0
    for agent_ip in dcos_api_session.slaves:
        response = dcos_api_session.metrics.get('/containers', node=agent_ip)
        assert response.status_code == 200
        num_containers += len(response.json())

    try:
        # install kafka framework
        install_response = dcos_api_session.cosmos.install_package('kafka', package_version='2.3.0-1.1.0')
        data = install_response.json()

        dcos_api_session.marathon.wait_for_deployments_complete()

        wait = True
        executor_mesos_id = task_mesos_id = kafka_task_name = ''
        while wait:
            master = dcos_api_session.masters[0]
            state_response = dcos_api_session.get('/state', host=master, port=5050)
            assert state_response.status_code == 200
            state = state_response.json()
            for framework in state['frameworks']:
                if framework['name'] == 'marathon':
                    for task in framework['tasks']:
                        if task['name'] == 'kafka':
                            executor_mesos_id = task['slave_id']
                            break
                elif framework['name'] == 'kafka' and len(framework['tasks']) > 0 and executor_mesos_id:
                    task_mesos_id = framework['tasks'][0]['slave_id']
                    kafka_task_name = framework['tasks'][0]['name']
                    wait = False
                    break

        for agent in state['slaves']:
            if agent['id'] == executor_mesos_id:
                executor_node = agent['hostname']
            if agent['id'] == task_mesos_id:
                task_node = agent['hostname']

        def task_checks(response):
            # check kafka task metric metadata
            for line in response.text.splitlines():
                if '#' in line:
                    continue
                # check that a kafka task's metric is appropriately tagged
                if kafka_task_name in line:
                    return ('service_name="kafka"' in line and
                            'task_name="{}"'.format(kafka_task_name) in line and
                            'executor_name="kafka"' in line)
            return False
        check_metrics_prom(dcos_api_session, task_node, task_checks)

        def executor_checks(response):
            # check kafka executor metric metadata
            for line in response.text.splitlines():
                if '#' in line:
                    continue
                # ignore metrics from kafka task started by marathon by checking
                # for absence of 'marathon' string.
                if 'cpus_nr_periods' in line and 'marathon' not in line:
                    return ('service_name="kafka"' in line and
                            'task_name=""' in line and  # this is an executor, not a task
                            'executor_name="kafka"' in line)
            return False
        check_metrics_prom(dcos_api_session, executor_node, executor_checks)
    finally:
        # uninstall and cleanup framework
        dcos_api_session.cosmos.uninstall_package('kafka', app_id=data['appId'])

        # Retry for 150 seconds for kafka teardown completion
        @retrying.retry(wait_fixed=2000, stop_max_delay=150 * 1000)
        def wait_for_framework_teardown():
            num_containers_check = 0
            for agent_ip in dcos_api_session.slaves:
                response = dcos_api_session.metrics.get('/containers', node=agent_ip)
                assert response.status_code == 200
                num_containers_check += len(response.json())
            assert num_containers_check <= num_containers

        wait_for_framework_teardown()


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


@common.xfailflake(reason="DCOS_OSS-4486 - tgest_metrics_containers fails with container metrics response status 204")
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
        if container_metrics['dimensions']['task_name'] == task_name:
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


@retrying.retry(wait_fixed=(2 * 1000), stop_max_delay=(30 * 1000))
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


@retrying.retry(wait_fixed=(2 * 1000), stop_max_delay=(30 * 1000))
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
