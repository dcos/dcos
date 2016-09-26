import retrying


LATENCY = 60


@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY * 1000)
def test_metrics_ping(cluster):
    """ Test that the metrics service is up.
    """
    for agent in cluster.slaves:
        response = cluster.metrics.get('ping', node=agent)
        assert response.status_code == 200, 'Got non-200 status code: {}'.format(response.content)
        'from private agent.'
        assert response.json()['ok'], 'Metrics /ping is not ok on private, got:\n{}'.format(response.content)
        'agent.'

    for agent in cluster.public_slaves:
        response = cluster.metrics.get('ping', node=agent)
        assert response.status_code == 200, 'Got non-200 status code: {}'.format(response.content)
        'from public agent.'
        assert response.json()['ok'], 'Metrics /ping is not ok on public agent, got:\n{}'.format(response.content)

    for master in cluster.masters:
        response = cluster.metrics.get('ping', node=master)
        assert response.status_code == 200, 'Got non-200 status code {}'.format(response.content)
        'from public agent.'
        assert response.json()['ok'], 'Metrics /ping is not ok on master, got:\n{}'.format(response.content)


@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY * 1000)
def test_metrics_node(cluster):
    """Test /system/metrics/api/v0/node endpoint returns
    correct metrics.
    """
    expected_node_metric_datapoints = [
        'uptime',
        'processes',
        'cpu.cores',
        'load.1min',
        'load.5min',
        'load.15min',
        'cpu.total',
        'cpu.user',
        'cpu.system',
        'cpu.idle',
        'cpu.wait',
        'memory.total',
        'memory.free',
        'memory.buffers',
        'memory.cached',
        'swap.total',
        'swam.free',
        'swap.used']

    def expected_datapoint_response(response):
        for datapoint in response["datapoints"]:
            if datapoint["name"] not in expected_node_metric_datapoints:
                return False
            return True

    for agent in cluster.slaves:
        response = cluster.metrics.get('node', node=agent)

        assert response.status_code == 200, 'Got non-200 status code '
        'from private agent for /node.'

        assert expected_datapoint_response(response.json()), 'Private agent did not '
        'return the expected metrics from .../node endpoint. '
        'Got {}'.format(response.json())

    for agent in cluster.public_slaves:
        response = cluster.metrics.get('node', node=agent)

        assert response.status_code == 200, 'Got non-200 status code '
        'from public agent for /node.'

        assert expected_datapoint_response(response.json()), 'Public agent did not '
        'return the expected metrics from .../node endpoint. '
        'Got {}'.format(response.json())

    for master in cluster.masters:
        response = cluster.metrics.get('node', node=master)

        assert response.status_code == 200, 'Got non-200 status code '
        'from master host for /node.'

        assert expected_datapoint_response(response.json()), 'Master host did not '
        'return the expected metrics from .../node endpoint. '
        'Got {}'.format(response.json())


def test_metrics_containers(cluster):
    """If there's a deployed container on the slave, iterate through them to check for
    the statsd-emitter executor. When found, query it's /app endpoint to test that
    it's sending the statsd metrics as expected.
    """
    @retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY * 1000)
    def test_containers(app_endpoints):
        for agent in app_endpoints:
            response = cluster.metrics.get('containers', node=agent.host)
            if len(response.json()) > 0:
                for c in response.json():

                    # Test that /containers/<id> responds with expected data
                    container_response = cluster.metrics.get('containers/{}'.format(c), node=agent.host)
                    if container_response.status_code == 200 and 'executor_id' in container_response.json():
                        # Executor ID value is "executor_id": "statsd-emitter.a094eed0-b017-11e6-a972-b2bcad3866cb"
                        assert 'statsd-emitter' in container_response.json()['executor_id'].split('.'), 'statsd-emitter'
                        ' was not found running on any slaves.'

                        # Test that /app response is responding with expected data
                        app_response = cluster.metrics.get('containers/{}/app'.format(c), node=agent.host)
                        if app_response.status_code == 200:
                            assert 'labels' in app_response.json(), '"labels" key not found in response.'
                            assert 'test_tag_key' in container_response.json()['labels'].items(), 'test-tag-key was not'
                            ' found in labels for statsd-emitter, expected test-tag-key key to be present.'

    marathon_config = {
        "id": "/statsd-emitter",
        "cmd": "/opt/mesosphere/bin/./statsd-emitter -debug",
        "cpus": 0.5,
        "mem": 128.0,
        "instances": 1
    }
    with cluster.marathon.deploy_and_cleanup(marathon_config, check_health=False) as app:
        assert len(app) == 1, 'The marathon app should have been deployed exactly once.'
        test_containers(app)
