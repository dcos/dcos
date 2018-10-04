import pytest
import retrying

__maintainer__ = 'mnaboka'
__contact__ = 'dcos-cluster-ops@mesosphere.io'


LATENCY = 60


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


@pytest.mark.parametrize("prometheus_port", [61091, 61092])
def test_metrics_masters_prom(dcos_api_session, prometheus_port):
    for master in dcos_api_session.masters:
        response = dcos_api_session.session.request('GET', 'http://' + master + ':{}/metrics'.format(prometheus_port))
        assert response.status_code == 200, 'Status code: {}'.format(response.status_code)


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
                        if dp['name'] == 'statsd_tester_time_uptime':
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

    @retrying.retry(wait_fixed=(2 * 1000), stop_max_delay=(150 * 1000))
    def _get_app_metric_datapoint_value_for_task(dcos_api_session, node: str, task_name: str, dp_name: str):
        app_metrics = get_app_metrics_for_task(dcos_api_session, node, task_name)
        assert app_metrics is not None, "missing metrics for task {}".format(task_name)
        dps = [dp for dp in app_metrics['datapoints'] if dp['name'] == dp_name]
        assert len(dps) == 1, 'expected 1 datapoint for metric {}, got {}'.format(dp_name, len(dps))
        return dps[0]['value']

    with dcos_api_session.marathon.deploy_and_cleanup(marathon_app, check_health=False):
        endpoints = dcos_api_session.marathon.get_app_service_endpoints(marathon_app['id'])
        assert len(endpoints) == 1, 'The marathon app should have been deployed exactly once.'
        node = endpoints[0].host

        # NaN should be converted to empty string.
        metric_value = _get_app_metric_datapoint_value_for_task(dcos_api_session, node, task_name, metric_name)
        assert metric_value == '', 'unexpected metric value: {}'.format(metric_value)


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


def test_pod_application_metrics(dcos_api_session):
    """Launch a pod, wait for its containers to be added to the metrics service,
    and then verify that:
    1) Container statistics metrics are provided for the executor container
    2) Application metrics are exposed for the task container
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

    @retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY * 1000)
    def test_application_metrics(agent_ip, agent_id, task_name, num_containers):
        debug_task_name = []

        # Retry for two and a half minutes since the collector collects
        # state every 2 minutes to propogate containers to the API
        @retrying.retry(wait_fixed=2000, stop_max_delay=150000)
        def wait_for_container_metrics_propogation():
            response = dcos_api_session.metrics.get('/containers', node=agent_ip)
            assert response.status_code == 200
            assert len(response.json()) == num_containers, 'Test should create {} containers'.format(num_containers)

        wait_for_container_metrics_propogation()

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

                # We expect three datapoints, could be in any order
                uptime_dp = None
                for dp in app_response.json()['datapoints']:
                    if dp['name'] == 'statsd_tester_time_uptime':
                        uptime_dp = dp
                        break

                # If this metric is missing, statsd-emitter's metrics were not received
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

                cid_registry = []
                for dp in container_response.json()['datapoints']:
                    # Verify expected tags are present.
                    assert 'tags' in dp, 'got {}'.format(dp)
                    expected_tag_names = {
                        'container_id',
                    }
                    if 'executor_name' in dp['tags']:
                        # If present, we want to make sure it has a valid value.
                        expected_tag_names.add('executor_name')
                    if dp['name'].startswith('blkio.'):
                        # blkio stats have 'blkio_device' tags.
                        expected_tag_names.add('blkio_device')
                    check_tags(dp['tags'], expected_tag_names)

                    # Ensure all container IDs in the response from the
                    # containers/<id> endpoint are the same.
                    cid_registry.append(dp['tags']['container_id'])
                    assert(check_cid(cid_registry))

                assert 'dimensions' in container_response.json(), 'got {}'.format(container_response.json())
                assert 'task_name' in container_response.json()['dimensions'], 'got {}'.format(
                    container_response.json()['dimensions'])

                debug_task_name.append(container_response.json()['dimensions']['task_name'])

                # Look for the specified task name.
                assert task_name.strip('/') == container_response.json()['dimensions']['task_name'],\
                    'Parent container was not tagged with the correct task name'

                # The executor container shouldn't expose application metrics.
                app_response = dcos_api_session.metrics.get('/containers/{}/app'.format(container_id), node=agent_ip)
                assert app_response.status_code == 204, 'got {}'.format(app_response.status_code)

                return True

    marathon_pod_config = {
        "id": "/statsd-emitter-task-group10",
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
                    "shell": "/mnt/mesos/sandbox/metrics_bin_dir/statsd-emitter"
                }
            },
            "volumeMounts": [{
                "name": "metricsbindir",
                "mountPath": "metrics_bin_dir"
            }]
        }],
        "volumes": [{
            "name": "metricsbindir",
            "host": "/opt/mesosphere/active/dcos-metrics/bin"
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
