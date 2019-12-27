import contextlib
import copy
import logging
import re
import sys
import uuid

import pytest
import retrying
from prometheus_client.parser import text_string_to_metric_families

from test_helpers import get_expanded_config


__maintainer__ = 'philipnrmn'
__contact__ = 'dcos-cluster-ops@mesosphere.io'


METRICS_WAITTIME = 5 * 60 * 1000
METRICS_INTERVAL = 2 * 1000
STD_WAITTIME = 15 * 60 * 1000
STD_INTERVAL = 5 * 1000

# tags added if a fault domain is present
FAULT_DOMAIN_TAGS = {'fault_domain_zone', 'fault_domain_region'}


def check_tags(tags: dict, required_tag_names: set, optional_tag_names: set = set()):
    """Assert that tags contains only expected keys with nonempty values."""
    keys = set(tags.keys())
    assert keys & required_tag_names == required_tag_names, 'Not all required tags were set'
    assert keys - required_tag_names - optional_tag_names == set(), 'Encountered unexpected tags'
    for tag_name, tag_val in tags.items():
        assert tag_val != '', 'Value for tag "%s" must not be empty'.format(tag_name)


@pytest.mark.supportedwindows
def test_metrics_ping(dcos_api_session):
    """ Test that the metrics service is up on master and agents.
    """
    nodes = get_master_and_agents(dcos_api_session)

    for node in nodes:
        response = dcos_api_session.metrics.get('/ping', node=node)
        assert response.status_code == 200, 'Status code: {}, Content {}'.format(response.status_code, response.content)
        assert response.json()['ok'], 'Status code: {}, Content {}'.format(response.status_code, response.content)


def test_metrics_agents_prom(dcos_api_session):
    """Telegraf Prometheus endpoint is reachable on master and agents."""
    nodes = get_master_and_agents(dcos_api_session)

    for node in nodes:
        response = dcos_api_session.session.request('GET', 'http://' + node + ':61091/metrics')
        assert response.status_code == 200, 'Status code: {}'.format(response.status_code)


@retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
def get_metrics_prom(dcos_api_session, node):
    """Gets metrics from prometheus port on node and returns the response.

    Retries on non-200 status for up to 300 seconds.

    """
    response = dcos_api_session.session.request(
        'GET', 'http://{}:61091/metrics'.format(node))
    assert response.status_code == 200, 'Status code: {}'.format(response.status_code)
    return response


def test_metrics_procstat(dcos_api_session):
    """Assert that procstat metrics are present on master and agent nodes."""
    nodes = get_master_and_agents(dcos_api_session)

    for node in nodes:
        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
        def check_procstat_metrics():
            response = get_metrics_prom(dcos_api_session, node)
            for family in text_string_to_metric_families(response.text):
                for sample in family.samples:
                    if sample[0] == 'procstat_lookup_pid_count':
                        return
            raise Exception('Expected Procstat procstat_lookup_pid_count metric not found')
        check_procstat_metrics()


def test_metrics_agents_mesos(dcos_api_session):
    """Assert that mesos metrics on agents are present."""
    nodes = get_agents(dcos_api_session)

    for node in nodes:
        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
        def check_mesos_metrics():
            response = get_metrics_prom(dcos_api_session, node)
            for family in text_string_to_metric_families(response.text):
                for sample in family.samples:
                    if sample[0] == 'mesos_slave_uptime_secs':
                        return
            raise Exception('Expected Mesos mesos_slave_uptime_secs metric not found')
        check_mesos_metrics()


def test_metrics_master_mesos(dcos_api_session):
    """Assert that mesos metrics on master are present."""
    @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
    def check_mesos_metrics():
        response = get_metrics_prom(dcos_api_session, dcos_api_session.masters[0])
        for family in text_string_to_metric_families(response.text):
            for sample in family.samples:
                if sample[0] == 'mesos_master_uptime_secs':
                    return
        raise Exception('Expected Mesos mesos_master_uptime_secs metric not found')
    check_mesos_metrics()


def test_metrics_agents_mesos_overlay(dcos_api_session):
    """Assert that mesos agent overlay module metrics on master and agents are present."""
    nodes = get_master_and_agents(dcos_api_session)

    for node in nodes:
        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
        def check_mesos_metrics():
            response = get_metrics_prom(dcos_api_session, node)
            for family in text_string_to_metric_families(response.text):
                for sample in family.samples:
                    if sample[0] == 'mesos_overlay_slave_registering':
                        return
            raise Exception('Expected Mesos mesos_overlay_slave_registering metric not found')
        check_mesos_metrics()


def test_metrics_master_mesos_overlay(dcos_api_session):
    """Assert that mesos overlay module metrics on master are present."""
    @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
    def check_mesos_metrics():
        response = get_metrics_prom(dcos_api_session, dcos_api_session.masters[0])
        for family in text_string_to_metric_families(response.text):
            for sample in family.samples:
                if sample[0] == 'mesos_overlay_master_process_restarts':
                    return
        raise Exception('Expected Mesos mesos_overlay_master_process_restarts metric not found')
    check_mesos_metrics()


def test_metrics_master_zookeeper(dcos_api_session):
    """Assert that ZooKeeper metrics on master are present."""
    @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
    def check_zookeeper_metrics():
        response = get_metrics_prom(dcos_api_session, dcos_api_session.masters[0])
        for family in text_string_to_metric_families(response.text):
            for sample in family.samples:
                if sample[0] == 'zookeeper_avg_latency':
                    assert sample[1]['dcos_component_name'] == 'ZooKeeper'
                    return
        raise Exception('Expected ZooKeeper zookeeper_avg_latency metric not found')
    check_zookeeper_metrics()


def test_metrics_master_cockroachdb(dcos_api_session):
    """Assert that CockroachDB metrics on master are present."""
    @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
    def check_cockroachdb_metrics():
        response = get_metrics_prom(dcos_api_session, dcos_api_session.masters[0])
        for family in text_string_to_metric_families(response.text):
            for sample in family.samples:
                if sample[0] == 'ranges_underreplicated':
                    assert sample[1]['dcos_component_name'] == 'CockroachDB'
                    return
        raise Exception('Expected CockroachDB ranges_underreplicated metric not found')
    check_cockroachdb_metrics()


def test_metrics_master_adminrouter_nginx_vts(dcos_api_session):
    """Assert that Admin Router Nginx VTS metrics on master are present."""
    @retrying.retry(
        wait_fixed=STD_INTERVAL,
        stop_max_delay=METRICS_WAITTIME,
        retry_on_exception=lambda e: isinstance(e, AssertionError)
    )
    def check_adminrouter_metrics():
        response = get_metrics_prom(dcos_api_session, dcos_api_session.masters[0])
        for family in text_string_to_metric_families(response.text):
            for sample in family.samples:
                if sample[0].startswith('nginx_vts_') and sample[1].get('dcos_component_name') == 'Admin Router':
                    return
        raise AssertionError('Expected Admin Router nginx_vts_* metrics not found')
    check_adminrouter_metrics()


def test_metrics_master_exhibitor_status(dcos_api_session):
    """Assert that Exhibitor status metrics on master are present."""
    @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
    def check_exhibitor_metrics():
        response = get_metrics_prom(dcos_api_session, dcos_api_session.masters[0])
        expected_metrics = {'exhibitor_status_code', 'exhibitor_status_isleader'}
        samples = []
        for family in text_string_to_metric_families(response.text):
            for sample in family.samples:
                if sample[0] in expected_metrics:
                    samples.append(sample)
        reported_metrics = {sample[0] for sample in samples}
        assert reported_metrics == expected_metrics, (
            'Expected Exhibitor status metrics not found. '
            'Expected: {} Reported: {}'.format(
                expected_metrics, reported_metrics,
            )
        )
        for sample in samples:
            assert sample[1]['dcos_component_name'] == 'Exhibitor'
            assert 'url' not in sample[1]
            assert 'exhibitor_address' in sample[1]
    check_exhibitor_metrics()


def _nginx_vts_measurement_basename(name: str) -> str:
    """
    Extracts the base name of the metric reported by nginx vts filter module
    and removes the metric suffix.

    E.g.: nginx_server_status_request_bytes -> nginx_server_status
    """
    return '_'.join(name.split('_')[:3])


def test_metrics_master_adminrouter_nginx_drop_requests_seconds(dcos_api_session):
    """
    nginx_vts_*_request_seconds* metrics are not present.
    """
    node = dcos_api_session.masters[0]
    # Make request to a fine-grained metrics annotated upstream of
    # Admin Router (IAM in this case).
    dcos_api_session.get('/acs/api/v1/auth/jwks', host=node)

    @retrying.retry(
        wait_fixed=STD_INTERVAL,
        stop_max_delay=METRICS_WAITTIME,
        retry_on_exception=lambda e: isinstance(e, AssertionError)
    )
    def check_adminrouter_metrics():
        vts_metrics_count = 0
        response = get_metrics_prom(dcos_api_session, node)
        for family in text_string_to_metric_families(response.text):
            for sample in family.samples:
                match = re.match(r'^nginx_vts_.+_request_seconds.*$', sample[0])
                assert match is None
                # We assert the validity of the test here by confirming that
                # VTS reported metrics have been scraped by telegraf.
                if sample[0].startswith('nginx_vts_'):
                    vts_metrics_count += 1
        assert vts_metrics_count > 0

    check_adminrouter_metrics()


def test_metrics_agent_adminrouter_nginx_drop_requests_seconds(dcos_api_session):
    """
    nginx_vts_*_request_seconds* metrics are not present.
    """
    # Make request to Admin Router on every agent to ensure metrics.
    state_response = dcos_api_session.get('/state', host=dcos_api_session.masters[0], port=5050)
    assert state_response.status_code == 200
    state = state_response.json()
    for agent in state['slaves']:
        agent_url = '/system/v1/agent/{}/dcos-metadata/dcos-version.json'.format(agent['id'])
        response = dcos_api_session.get(agent_url)
        assert response.status_code == 200

    nodes = get_agents(dcos_api_session)
    for node in nodes:
        @retrying.retry(
            wait_fixed=STD_INTERVAL,
            stop_max_delay=METRICS_WAITTIME,
            retry_on_exception=lambda e: isinstance(e, AssertionError)
        )
        def check_adminrouter_metrics():
            vts_metrics_count = 0
            response = get_metrics_prom(dcos_api_session, node)
            for family in text_string_to_metric_families(response.text):
                for sample in family.samples:
                    match = re.match(r'^nginx_vts_.+_request_seconds.*$', sample[0])
                    assert match is None
                    # We assert the validity of the test here by confirming that
                    # VTS reported metrics have been scraped by telegraf.
                    if sample[0].startswith('nginx_vts_'):
                        vts_metrics_count += 1
            assert vts_metrics_count > 0

        check_adminrouter_metrics()


def test_metrics_master_adminrouter_nginx_vts_processor(dcos_api_session):
    """Assert that processed Admin Router metrics on master are present."""
    node = dcos_api_session.masters[0]
    # Make request to a fine-grained metrics annotated upstream of
    # Admin Router (IAM in this case).
    r = dcos_api_session.get('/acs/api/v1/auth/jwks', host=node)
    assert r.status_code == 200

    # Accessing /service/marathon/v2/queue via Admin Router will cause
    # Telegraf to emit nginx_service_backend and nginx_service_status metrics.
    r = dcos_api_session.get('/service/marathon/v2/queue', host=node)
    assert r.status_code == 200

    @retrying.retry(
        wait_fixed=STD_INTERVAL,
        stop_max_delay=METRICS_WAITTIME,
        retry_on_exception=lambda e: isinstance(e, AssertionError)
    )
    def check_adminrouter_metrics():
        measurements = set()
        expect_dropped = set([
            'nginx_vts_filter',
            'nginx_vts_upstream',
            'nginx_vts_server',
        ])
        unexpected_samples = []

        response = get_metrics_prom(dcos_api_session, node)
        for family in text_string_to_metric_families(response.text):
            for sample in family.samples:
                if sample[0].startswith('nginx_') and sample[1].get('dcos_component_name') == 'Admin Router':
                    basename = _nginx_vts_measurement_basename(sample[0])
                    measurements.add(basename)
                    if basename in expect_dropped:
                        unexpected_samples.append(sample)

        assert unexpected_samples == []

        expected = set([
            'nginx_server_status',
            'nginx_upstream_status',
            'nginx_upstream_backend',
            'nginx_service_backend',
            'nginx_service_status',
        ])

        difference = expected - measurements
        assert not difference

        remainders = expect_dropped & measurements
        assert not remainders
    check_adminrouter_metrics()


def test_metrics_agents_adminrouter_nginx_vts(dcos_api_session):
    """Assert that Admin Router Nginx VTS metrics on agents are present."""
    nodes = get_agents(dcos_api_session)

    for node in nodes:
        @retrying.retry(
            wait_fixed=STD_INTERVAL,
            stop_max_delay=METRICS_WAITTIME,
            retry_on_exception=lambda e: isinstance(e, AssertionError)
        )
        def check_adminrouter_metrics():
            response = get_metrics_prom(dcos_api_session, node)
            for family in text_string_to_metric_families(response.text):
                for sample in family.samples:
                    if (
                        sample[0].startswith('nginx_vts_') and
                        sample[1].get('dcos_component_name') == 'Admin Router Agent'
                    ):
                        return
            raise AssertionError('Expected Admin Router nginx_vts_* metrics not found')
        check_adminrouter_metrics()


def test_metrics_agent_adminrouter_nginx_vts_processor(dcos_api_session):
    """Assert that processed Admin Router metrics on agent are present."""
    # Make request to Admin Router on every agent to ensure metrics.
    state_response = dcos_api_session.get('/state', host=dcos_api_session.masters[0], port=5050)
    assert state_response.status_code == 200
    state = state_response.json()
    for agent in state['slaves']:
        agent_url = '/system/v1/agent/{}/dcos-metadata/dcos-version.json'.format(agent['id'])
        response = dcos_api_session.get(agent_url)
        assert response.status_code == 200

    nodes = get_agents(dcos_api_session)
    for node in nodes:
        @retrying.retry(
            wait_fixed=STD_INTERVAL,
            stop_max_delay=METRICS_WAITTIME,
            retry_on_exception=lambda e: isinstance(e, AssertionError)
        )
        def check_adminrouter_metrics():
            measurements = set()
            expect_dropped = set([
                'nginx_vts_filter',
                'nginx_vts_upstream',
                'nginx_vts_server',
            ])
            unexpected_samples = []

            response = get_metrics_prom(dcos_api_session, node)
            for family in text_string_to_metric_families(response.text):
                for sample in family.samples:
                    if sample[0].startswith('nginx_') and sample[1].get('dcos_component_name') == 'Admin Router Agent':
                        basename = _nginx_vts_measurement_basename(sample[0])
                        measurements.add(basename)
                        if basename in expect_dropped:
                            unexpected_samples.append(sample)

            assert unexpected_samples == []

            expected = set([
                'nginx_server_status',
            ])
            difference = expected - measurements
            assert not difference

            remainders = expect_dropped & measurements
            assert not remainders
        check_adminrouter_metrics()


def test_metrics_diagnostics(dcos_api_session):
    """Assert that DC/OS Diagnostics metrics on master are present."""
    nodes = get_master_and_agents(dcos_api_session)

    for node in nodes:
        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
        def check_diagnostics_metrics():
            response = get_metrics_prom(dcos_api_session, node)
            for family in text_string_to_metric_families(response.text):
                for sample in family.samples:
                    if sample[0].startswith('bundle_creation_time_seconds'):
                        assert sample[1]['dcos_component_name'] == 'DC/OS Diagnostics'
                        return
            raise Exception('Expected DC/OS Diagnostics metrics not found')
        check_diagnostics_metrics()


def test_metrics_fluentbit(dcos_api_session):
    """Ensure that fluent bit metrics are present on masters and agents"""
    nodes = get_master_and_agents(dcos_api_session)

    for node in nodes:
        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
        def check_fluentbit_metrics():
            response = get_metrics_prom(dcos_api_session, node)
            for family in text_string_to_metric_families(response.text):
                for sample in family.samples:
                    if sample[0].startswith('fluentbit_output_errors_total'):
                        assert sample[1]['dcos_component_name'] == 'DC/OS Fluent Bit'
                        return
            raise Exception('Expected DC/OS Fluent Bit metrics not found')
        check_fluentbit_metrics()


def check_statsd_app_metrics(dcos_api_session, marathon_app, node, expected_metrics):
    with dcos_api_session.marathon.deploy_and_cleanup(marathon_app, check_health=False):
        endpoints = dcos_api_session.marathon.get_app_service_endpoints(marathon_app['id'])
        assert len(endpoints) == 1, 'The marathon app should have been deployed exactly once.'

        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
        def check_statsd_metrics():
            expected_copy = copy.deepcopy(expected_metrics)
            response = get_metrics_prom(dcos_api_session, node)
            for family in text_string_to_metric_families(response.text):
                for sample in family.samples:
                    if sample[0] in expected_copy:
                        val = expected_copy.pop(sample[0])
                        assert sample[2] == val
                        if len(expected_copy) == 0:
                            return
            sys.stderr.write(
                "%r\n%r\n" % (
                    expected_metrics,
                    expected_copy,
                )
            )
            raise Exception('Expected statsd metrics not found')
        check_statsd_metrics()


def test_metrics_agent_statsd(dcos_api_session):
    """Assert that statsd metrics on private agent are present."""
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
            # pin image to working version - https://jira.mesosphere.com/browse/DCOS-62478
            'docker': {'image': 'library/alpine:3.10.3'}
        },
        'networks': [{'mode': 'host'}],
    }
    expected_metrics = {
        metric_name_pfx + '_gauge': 100.0,
        # NOTE: prometheus_client appends _total to counter-type metrics if they don't already have the suffix
        # ref: https://github.com/prometheus/client_python/blob/master/prometheus_client/parser.py#L169
        # (the raw prometheus output here omits _total)
        metric_name_pfx + '_count_total': 1.0,
        metric_name_pfx + '_timing_count': 1.0,
        metric_name_pfx + '_histogram_count': 1.0,
    }

    if dcos_api_session.slaves:
        marathon_app['constraints'] = [['hostname', 'LIKE', dcos_api_session.slaves[0]]]
        check_statsd_app_metrics(dcos_api_session, marathon_app, dcos_api_session.slaves[0], expected_metrics)

    if dcos_api_session.public_slaves:
        marathon_app['acceptedResourceRoles'] = ["slave_public"]
        marathon_app['constraints'] = [['hostname', 'LIKE', dcos_api_session.public_slaves[0]]]
        check_statsd_app_metrics(dcos_api_session, marathon_app, dcos_api_session.public_slaves[0], expected_metrics)


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

            # Rarely, the framework will continue to show up in 'frameworks' instead of
            # 'completed_frameworks', even after teardown. To avoid this causing a test
            # failure, if the framework continues to show up in 'frameworks', we instead
            # check if there are any running tasks.
            frameworks = {f['name']: f for f in state['frameworks']}
            assert framework_name not in frameworks or len(
                frameworks[framework_name]['tasks']) == 0, 'Framework {} still running'.format(framework_name)
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


def test_task_metrics_metadata(dcos_api_session):
    """Test that task metrics have expected metadata/labels"""
    expanded_config = get_expanded_config()
    if expanded_config.get('security') == 'strict':
        pytest.skip('MoM disabled for strict mode')
    with deploy_and_cleanup_dcos_package(dcos_api_session, 'marathon', '1.6.535', 'marathon-user'):
        node = get_task_hostname(dcos_api_session, 'marathon', 'marathon-user')

        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
        def check_metrics_metadata():
            response = get_metrics_prom(dcos_api_session, node)
            for family in text_string_to_metric_families(response.text):
                for sample in family.samples:
                    if sample[1].get('task_name') == 'marathon-user':
                        assert sample[1]['service_name'] == 'marathon'
                        # check for whitelisted label
                        assert sample[1]['DCOS_SERVICE_NAME'] == 'marathon-user'
                        return
            raise Exception('Expected marathon task metrics not found')
        check_metrics_metadata()


def test_executor_metrics_metadata(dcos_api_session):
    """Test that executor metrics have expected metadata/labels"""
    expanded_config = get_expanded_config()
    if expanded_config.get('security') == 'strict':
        pytest.skip('Framework disabled for strict mode')

    with deploy_and_cleanup_dcos_package(dcos_api_session, 'hello-world', '2.2.0-0.42.2', 'hello-world'):
        node = get_task_hostname(dcos_api_session, 'marathon', 'hello-world')

        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
        def check_executor_metrics_metadata():
            response = get_metrics_prom(dcos_api_session, node)
            for family in text_string_to_metric_families(response.text):
                for sample in family.samples:
                    if sample[0] == 'cpus_nr_periods' and sample[1].get('service_name') == 'hello-world':
                        assert sample[1]['task_name'] == ''
                        # hello-world executors can be named "hello" or "world"
                        assert (sample[1]['executor_name'] == 'hello' or sample[1]['executor_name'] == 'world')
                        return
            raise Exception('Expected hello-world executor metrics not found')
        check_executor_metrics_metadata()


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

    # Retry for 5 minutes for for the node metrics content to appear.
    @retrying.retry(stop_max_delay=METRICS_WAITTIME)
    def wait_for_node_response(node):
        response = dcos_api_session.metrics.get('/node', node=node)
        assert response.status_code == 200
        return response

    nodes = get_master_and_agents(dcos_api_session)

    for node in nodes:
        response = wait_for_node_response(node)

        assert response.status_code == 200, 'Status code: {}, Content {}'.format(
            response.status_code, response.content)
        assert expected_datapoint_response(response.json())
        assert expected_dimension_response(response.json())


def get_master_and_agents(dcos_api_session):
    nodes = [dcos_api_session.masters[0]]
    nodes.extend(get_agents(dcos_api_session))
    return nodes


def get_agents(dcos_api_session):
    nodes = []
    if dcos_api_session.slaves:
        nodes.append(dcos_api_session.slaves[0])
    if dcos_api_session.public_slaves:
        nodes.append(dcos_api_session.public_slaves[0])
    return nodes


def test_metrics_containers(dcos_api_session):
    """Assert that a Marathon app's container and app metrics can be retrieved."""
    @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
    def test_containers(app_endpoints):
        for agent in app_endpoints:
            container_metrics, app_metrics = get_metrics_for_task(dcos_api_session, agent.host, 'statsd-emitter')

            # Check container metrics.
            # Check tags on each datapoint.
            cid_registry = set()
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
                check_tags(dp['tags'], expected_tag_names, FAULT_DOMAIN_TAGS)

                # Ensure all container ID's in the container/<id> endpoint are
                # the same.
                cid_registry.add(dp['tags']['container_id'])

            assert len(cid_registry) == 1, 'Not all container IDs in the metrics response are equal'

            # Check app metrics.
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

            # If fault domain is enabled, ensure that fault domain tags are present
            expanded_config = get_expanded_config()
            if expanded_config.get('fault_domain_enabled') == 'true':
                expected_tag_names |= FAULT_DOMAIN_TAGS

            check_tags(uptime_dp['tags'], expected_tag_names)
            assert uptime_dp['tags']['test_tag_key'] == 'test_tag_value', 'got {}'.format(uptime_dp)
            assert uptime_dp['value'] > 0

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


def test_statsd_metrics_containers_app(dcos_api_session):
    """Assert that statsd app metrics appear in the v0 metrics API."""
    task_name = 'test-statsd-metrics-containers-app'
    metric_name_pfx = 'test_statsd_metrics_containers_app'
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


def test_prom_metrics_containers_app_host(dcos_api_session):
    """Assert that prometheus app metrics appear in the v0 metrics API."""
    task_name = 'test-prom-metrics-containers-app-host'
    metric_name_pfx = 'test_prom_metrics_containers_app_host'
    marathon_app = {
        'id': '/' + task_name,
        'instances': 1,
        'cpus': 0.1,
        'mem': 128,
        'cmd': '\n'.join([
            'echo "Creating metrics file..."',
            'touch metrics',

            'echo "# TYPE {}_gauge gauge" >> metrics'.format(metric_name_pfx),
            'echo "{}_gauge 100" >> metrics'.format(metric_name_pfx),

            'echo "# TYPE {}_count counter" >> metrics'.format(metric_name_pfx),
            'echo "{}_count 2" >> metrics'.format(metric_name_pfx),

            'echo "# TYPE {}_histogram histogram" >> metrics'.format(metric_name_pfx),
            'echo "{}_histogram_bucket{{le=\\"+Inf\\"}} 4" >> metrics'.format(metric_name_pfx),
            'echo "{}_histogram_sum 4" >> metrics'.format(metric_name_pfx),
            'echo "{}_histogram_seconds_count 4" >> metrics'.format(metric_name_pfx),

            'echo "Serving prometheus metrics on http://localhost:$PORT0"',
            'python3 -m http.server $PORT0',
        ]),
        'container': {
            'type': 'MESOS',
            'docker': {'image': 'library/python:3'}
        },
        'portDefinitions': [{
            'protocol': 'tcp',
            'port': 0,
            'labels': {'DCOS_METRICS_FORMAT': 'prometheus'},
        }],
    }

    logging.debug('Starting marathon app with config: %s', marathon_app)
    expected_metrics = [
        # metric_name, metric_value
        ('_'.join([metric_name_pfx, 'gauge.gauge']), 100),
        ('_'.join([metric_name_pfx, 'count.counter']), 2),
        ('_'.join([metric_name_pfx, 'histogram_seconds', 'count']), 4),
    ]

    with dcos_api_session.marathon.deploy_and_cleanup(marathon_app, check_health=False):
        endpoints = dcos_api_session.marathon.get_app_service_endpoints(marathon_app['id'])
        assert len(endpoints) == 1, 'The marathon app should have been deployed exactly once.'
        node = endpoints[0].host
        for metric_name, metric_value in expected_metrics:
            assert_app_metric_value_for_task(dcos_api_session, node, task_name, metric_name, metric_value)


def test_prom_metrics_containers_app_bridge(dcos_api_session):
    """Assert that prometheus app metrics appear in the v0 metrics API."""
    task_name = 'test-prom-metrics-containers-app-bridge'
    metric_name_pfx = 'test_prom_metrics_containers_app_bridge'
    marathon_app = {
        'id': '/' + task_name,
        'instances': 1,
        'cpus': 0.1,
        'mem': 128,
        'cmd': '\n'.join([
            'echo "Creating metrics file..."',
            'touch metrics',

            'echo "# TYPE {}_gauge gauge" >> metrics'.format(metric_name_pfx),
            'echo "{}_gauge 100" >> metrics'.format(metric_name_pfx),

            'echo "# TYPE {}_count counter" >> metrics'.format(metric_name_pfx),
            'echo "{}_count 2" >> metrics'.format(metric_name_pfx),

            'echo "# TYPE {}_histogram histogram" >> metrics'.format(metric_name_pfx),
            'echo "{}_histogram_bucket{{le=\\"+Inf\\"}} 4" >> metrics'.format(metric_name_pfx),
            'echo "{}_histogram_sum 4" >> metrics'.format(metric_name_pfx),
            'echo "{}_histogram_seconds_count 4" >> metrics'.format(metric_name_pfx),

            'echo "Serving prometheus metrics on http://localhost:8000"',
            'python3 -m http.server 8000',
        ]),
        'networks': [{'mode': 'container/bridge'}],
        'container': {
            'type': 'MESOS',
            'docker': {'image': 'library/python:3'},
            'portMappings': [
                {
                    'containerPort': 8000,
                    'hostPort': 0,
                    'protocol': 'tcp',
                    'labels': {'DCOS_METRICS_FORMAT': 'prometheus'},
                }
            ]
        },
    }

    logging.debug('Starting marathon app with config: %s', marathon_app)
    expected_metrics = [
        # metric_name, metric_value
        ('_'.join([metric_name_pfx, 'gauge.gauge']), 100),
        ('_'.join([metric_name_pfx, 'count.counter']), 2),
        ('_'.join([metric_name_pfx, 'histogram_seconds', 'count']), 4),
    ]

    with dcos_api_session.marathon.deploy_and_cleanup(marathon_app, check_health=False):
        endpoints = dcos_api_session.marathon.get_app_service_endpoints(marathon_app['id'])
        assert len(endpoints) == 1, 'The marathon app should have been deployed exactly once.'
        node = endpoints[0].host
        for metric_name, metric_value in expected_metrics:
            assert_app_metric_value_for_task(dcos_api_session, node, task_name, metric_name, metric_value)


def test_task_prom_metrics_not_filtered(dcos_api_session):
    """Assert that prometheus app metrics aren't filtered according to adminrouter config.

    This is a regression test protecting a fix for a bug that mistakenly applied filter criteria intended for
    adminrouter metrics to Prometheus-formatted metrics gathered from tasks.

    """
    task_name = 'test-task-prom-metrics-not-filtered'
    metric_name_pfx = 'test_task_prom_metrics_not_filtered'
    marathon_app = {
        'id': '/' + task_name,
        'instances': 1,
        'cpus': 0.1,
        'mem': 128,
        'cmd': '\n'.join([
            # Serve metrics that would be dropped by Telegraf were they collected from the adminrouter. These are task
            # metrics, so we expect Telegraf to gather and output them.
            'echo "Creating metrics file..."',

            # Adminrouter metrics with direction="[1-5]xx" tags get dropped.
            'echo "# TYPE {}_gauge gauge" >> metrics'.format(metric_name_pfx),
            'echo "{}_gauge{{direction=\\"1xx\\"}} 100" >> metrics'.format(metric_name_pfx),

            # Adminrouter metrics with these names get dropped.
            'echo "# TYPE nginx_vts_filter_cache_foo gauge" >> metrics',
            'echo "nginx_vts_filter_cache_foo 100" >> metrics',
            'echo "# TYPE nginx_vts_server_foo gauge" >> metrics',
            'echo "nginx_vts_server_foo 100" >> metrics',
            'echo "# TYPE nginx_vts_upstream_foo gauge" >> metrics',
            'echo "nginx_vts_upstream_foo 100" >> metrics',
            'echo "# TYPE nginx_vts_foo_request_seconds gauge" >> metrics',
            'echo "nginx_vts_foo_request_seconds 100" >> metrics',

            'echo "Serving prometheus metrics on http://localhost:8000"',
            'python3 -m http.server 8000',
        ]),
        'networks': [{'mode': 'container/bridge'}],
        'container': {
            'type': 'MESOS',
            'docker': {'image': 'library/python:3'},
            'portMappings': [
                {
                    'containerPort': 8000,
                    'hostPort': 0,
                    'protocol': 'tcp',
                    'labels': {'DCOS_METRICS_FORMAT': 'prometheus'},
                }
            ]
        },
    }

    logging.debug('Starting marathon app with config: %s', marathon_app)
    expected_metrics = [
        # metric_name, metric_value
        ('_'.join([metric_name_pfx, 'gauge.gauge']), 100),
        ('nginx_vts_filter_cache_foo.gauge', 100),
        ('nginx_vts_server_foo.gauge', 100),
        ('nginx_vts_upstream_foo.gauge', 100),
        ('nginx_vts_foo_request_seconds.gauge', 100),
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
    _, app_metrics = get_metrics_for_task(dcos_api_session, node, task_name)
    assert app_metrics is not None, "missing metrics for task {}".format(task_name)
    dps = [dp for dp in app_metrics['datapoints'] if dp['name'] == metric_name]
    assert len(dps) == 1, 'expected 1 datapoint for metric {}, got {}'.format(metric_name, len(dps))
    return dps[0]


# Retry for 5 minutes since the collector collects state
# every 2 minutes to propogate containers to the API
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


@retrying.retry(wait_fixed=METRICS_INTERVAL, stop_max_delay=METRICS_WAITTIME)
def get_container_metrics(dcos_api_session, node: str, container_id: str):
    """Return container_id's metrics from the metrics API on node.

    Returns None on 204.

    Retries on error, non-200 status, or missing response fields for up
    to 5 minutes.

    """
    response = dcos_api_session.metrics.get('/containers/' + container_id, node=node)

    if response.status_code == 204:
        return None

    assert response.status_code == 200
    container_metrics = response.json()

    assert 'datapoints' in container_metrics, (
        'container metrics must include datapoints. Got: {}'.format(container_metrics)
    )
    assert 'dimensions' in container_metrics, (
        'container metrics must include dimensions. Got: {}'.format(container_metrics)
    )

    return container_metrics


@retrying.retry(wait_fixed=METRICS_INTERVAL, stop_max_delay=METRICS_WAITTIME)
def get_app_metrics(dcos_api_session, node: str, container_id: str):
    """Return app metrics for container_id from the metrics API on node.

    Returns None on 204.

    Retries on error or non-200 status for up to 5 minutes.

    """
    resp = dcos_api_session.metrics.get('/containers/' + container_id + '/app', node=node)

    if resp.status_code == 204:
        return None

    assert resp.status_code == 200, 'got {}'.format(resp.status_code)
    app_metrics = resp.json()

    assert 'datapoints' in app_metrics, 'got {}'.format(app_metrics)
    assert 'dimensions' in app_metrics, 'got {}'.format(app_metrics)

    return app_metrics


@retrying.retry(wait_fixed=METRICS_INTERVAL, stop_max_delay=METRICS_WAITTIME)
def get_metrics_for_task(dcos_api_session, node: str, task_name: str):
    """Return (container_metrics, app_metrics) for task_name on node.

    Retries on error, non-200 responses, or missing metrics for task_name for
    up to 5 minutes.

    """
    task_names_seen = []  # Used for exception message if task_name can't be found.

    for cid in get_container_ids(dcos_api_session, node):
        container_metrics = get_container_metrics(dcos_api_session, node, cid)

        if container_metrics is None:
            task_names_seen.append((cid, None))
            continue

        if container_metrics['dimensions'].get('task_name') != task_name:
            task_names_seen.append((cid, container_metrics['dimensions'].get('task_name')))
            continue

        app_metrics = get_app_metrics(dcos_api_session, node, cid)
        return container_metrics, app_metrics

    raise Exception(
        'No metrics found for task {} on host {}. Task names seen: {}'.format(task_name, node, task_names_seen)
    )


def test_standalone_container_metrics(dcos_api_session):
    """
    An operator should be able to launch a standalone container using the
    LAUNCH_CONTAINER call of the agent operator API. Additionally, if the
    process running within the standalone container emits statsd metrics, they
    should be accessible via the DC/OS metrics API.
    """
    expanded_config = get_expanded_config()
    if expanded_config.get('security') == 'strict':
        reason = (
            'Only resource providers are authorized to launch standalone '
            'containers in strict mode. See DCOS-42325.'
        )
        pytest.skip(reason)
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
    # available via the metrics service. Because of this, we wait up to 5
    # minutes for these metrics to appear before throwing an exception.
    def _should_retry_metrics_fetch(response):
        return response.status_code == 204

    @retrying.retry(wait_fixed=METRICS_INTERVAL,
                    stop_max_delay=METRICS_WAITTIME,
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

        assert 'datapoints' in metrics_response, 'got {}'.format(metrics_response)

        uptime_dp = None
        for dp in metrics_response['datapoints']:
            if dp['name'] == 'statsd_tester.time.uptime':
                uptime_dp = dp
                break

        # If this metric is missing, statsd-emitter's metrics were not received
        assert uptime_dp is not None, 'got {}'.format(metrics_response)

        datapoint_keys = ['name', 'value', 'unit', 'timestamp', 'tags']
        for k in datapoint_keys:
            assert k in uptime_dp, 'got {}'.format(uptime_dp)

        expected_tag_names = {
            'dcos_cluster_id',
            'test_tag_key',
            'dcos_cluster_name',
            'host'
        }
        check_tags(uptime_dp['tags'], expected_tag_names, FAULT_DOMAIN_TAGS)
        assert uptime_dp['tags']['test_tag_key'] == 'test_tag_value', 'got {}'.format(uptime_dp)
        assert uptime_dp['value'] > 0

        assert 'dimensions' in metrics_response, 'got {}'.format(metrics_response)
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
    @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
    def test_application_metrics(agent_ip, agent_id, task_name, num_containers):
        # Get expected 2 container ids from mesos state endpoint
        # (one container + its parent container)
        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
        def get_container_ids_from_state(dcos_api_session, num_containers):
            state_response = dcos_api_session.get('/state', host=dcos_api_session.masters[0], port=5050)
            assert state_response.status_code == 200
            state = state_response.json()

            cids = set()
            for framework in state['frameworks']:
                if framework['name'] == 'marathon':
                    for task in framework['tasks']:
                        if task['name'] == 'statsd-emitter-task':
                            container = task['statuses'][0]['container_status']['container_id']
                            cids.add(container['value'])
                            if 'parent' in container:
                                cids.add(container['parent']['value'])
                            break
                    break

            assert len(cids) == num_containers, 'Test should create {} containers'.format(num_containers)
            return cids

        container_ids = get_container_ids_from_state(dcos_api_session, num_containers)

        # Retry for two and a half minutes since the collector collects
        # state every 2 minutes to propagate containers to the API
        @retrying.retry(wait_fixed=STD_INTERVAL, stop_max_delay=METRICS_WAITTIME)
        def wait_for_container_metrics_propagation(container_ids):
            response = dcos_api_session.metrics.get('/containers', node=agent_ip)
            assert response.status_code == 200
            assert container_ids.issubset(
                response.json()), "Containers {} should have been propagated".format(container_ids)

        wait_for_container_metrics_propagation(container_ids)

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
        mesos_agent_cids = [container['container_id']['value'] for container in mesos_agent_containers]
        assert container_ids.issubset(mesos_agent_cids), "Missing expected containers {}".format(container_ids)

        def is_nested_container(container):
            """Helper to check whether or not a container returned in the
            GET_CONTAINERS response is a nested container.
            """
            return 'parent' in container['container_status']['container_id']

        for container in mesos_agent_containers:
            container_id = container['container_id']['value']

            # Test that /containers/<id> responds with expected data.
            container_id_path = '/containers/{}'.format(container_id)

            if (is_nested_container(container)):
                # Retry for 5 minutes for each nested container to appear.
                # Since nested containers do not report resource statistics, we
                # expect the response code to be 204.
                @retrying.retry(stop_max_delay=METRICS_WAITTIME)
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
                    if dp['name'] == 'statsd_tester.time.uptime':
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
                check_tags(uptime_dp['tags'], expected_tag_names, FAULT_DOMAIN_TAGS)
                assert uptime_dp['tags']['test_tag_key'] == 'test_tag_value', 'got {}'.format(uptime_dp)
                assert uptime_dp['value'] > 0

                assert 'dimensions' in app_response.json(), 'got {}'.format(app_response.json())
                assert 'task_name' in app_response.json()['dimensions'], 'got {}'.format(
                    app_response.json()['dimensions'])

                # Look for the specified task name.
                assert task_name.strip('/') == app_response.json()['dimensions']['task_name'],\
                    'Nested container was not tagged with the correct task name'
            else:
                # Retry for 5 minutes for each parent container to present its
                # content.
                @retrying.retry(stop_max_delay=METRICS_WAITTIME)
                def wait_for_container_response():
                    response = dcos_api_session.metrics.get(container_id_path, node=agent_ip)
                    assert response.status_code == 200
                    return response

                container_response = wait_for_container_response()
                assert 'datapoints' in container_response.json(), 'got {}'.format(container_response.json())

                cid_registry = set()
                for dp in container_response.json()['datapoints']:
                    # Verify expected tags are present.
                    assert 'tags' in dp, 'got {}'.format(dp)
                    expected_tag_names = {
                        'container_id',
                    }
                    if dp['name'].startswith('blkio.'):
                        # blkio stats have 'blkio_device' tags.
                        expected_tag_names.add('blkio_device')
                    check_tags(dp['tags'], expected_tag_names, FAULT_DOMAIN_TAGS)

                    # Ensure all container IDs in the response from the
                    # containers/<id> endpoint are the same.
                    cid_registry.add(dp['tags']['container_id'])

                assert len(cid_registry) == 1, 'Not all container IDs in the metrics response are equal'

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
