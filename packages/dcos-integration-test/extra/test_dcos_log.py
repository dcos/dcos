import json
import uuid

import requests
import retrying


def validate_json_entry(entry: dict):
    required_fields = {'fields', 'cursor', 'monotonic_timestamp', 'realtime_timestamp'}

    assert set(entry.keys()) <= required_fields, (
        "Entry didn't have all required fields. Entry fields: {}, required fields:{}".format(entry, required_fields))

    assert entry['fields'], '`fields` cannot be empty dict. Got {}'.format(entry)


def validate_sse_entry(entry):
    assert entry, 'Expect at least one line. Got {}'.format(entry)
    entry_json = json.loads(entry.lstrip('data: '))
    validate_json_entry(entry_json)


def check_response_ok(response: requests.models.Response, headers: dict):
    assert response.ok, 'Request {} returned response code {}'.format(response.url, response.status_code)
    for name, value in headers.items():
        assert response.headers.get(name) == value, (
            'Request {} header {} must be {}. All headers {}'.format(response.url, name, value, response.headers))


def test_log_text(dcos_api_session):
    for node in dcos_api_session.masters + dcos_api_session.all_slaves:
        response = dcos_api_session.logs.get('v1/range/?limit=10', node=node)
        check_response_ok(response, {'Content-Type': 'text/plain'})

        # expect 10 lines
        lines = list(filter(lambda x: x != '', response.content.decode().split('\n')))
        assert len(lines) == 10, 'Expect 10 log entries. Got {}. All lines {}'.format(len(lines), lines)


def test_log_json(dcos_api_session):
    for node in dcos_api_session.masters + dcos_api_session.all_slaves:
        response = dcos_api_session.logs.get('v1/range/?limit=1', node=node, headers={'Accept': 'application/json'})
        check_response_ok(response, {'Content-Type': 'application/json'})
        validate_json_entry(response.json())


def test_log_server_sent_events(dcos_api_session):
    for node in dcos_api_session.masters + dcos_api_session.all_slaves:
        response = dcos_api_session.logs.get('v1/range/?limit=1', node=node, headers={'Accept': 'text/event-stream'})
        check_response_ok(response, {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache'})
        validate_sse_entry(response.text)


def test_stream(dcos_api_session):
    for node in dcos_api_session.masters + dcos_api_session.all_slaves:
        response = dcos_api_session.logs.get('v1/stream/?skip_prev=1', node=node, stream=True,
                                             headers={'Accept': 'text/event-stream'})
        check_response_ok(response, {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache'})
        lines = response.iter_lines()
        sse_id = next(lines)
        assert sse_id, 'First line must be id. Got {}'.format(sse_id)
        data = next(lines).decode('utf-8', 'ignore')
        validate_sse_entry(data)


def test_log_proxy(dcos_api_session):
    r = dcos_api_session.get('/mesos/master/slaves')
    check_response_ok(r, {})

    data = r.json()
    slaves_ids = sorted(x['id'] for x in data['slaves'] if x['hostname'] in dcos_api_session.all_slaves)

    for slave_id in slaves_ids:
        response = dcos_api_session.get('/system/v1/agent/{}/logs/v1/range/?skip_prev=10&limit=10'.format(slave_id))
        check_response_ok(response, {'Content-Type': 'text/plain'})
        lines = list(filter(lambda x: x != '', response.text.split('\n')))
        assert len(lines) == 10, 'Expect 10 log entries. Got {}. All lines {}'.format(len(lines), lines)


def test_task_logs(dcos_api_session):
    test_uuid = uuid.uuid4().hex

    task_id = "integration-test-task-logs-{}".format(test_uuid)

    task_definition = {
        "id": "/{}".format(task_id),
        "cpus": 0.1,
        "instances": 1,
        "mem": 128,
        "cmd": "echo STDOUT_LOG; echo STDERR_LOG >&2;sleep 999"
    }

    with dcos_api_session.marathon.deploy_and_cleanup(task_definition, check_health=False):
        url = get_task_url(dcos_api_session, task_id)
        check_log_entry('STDOUT_LOG', url + '?filter=STREAM:STDOUT', dcos_api_session)
        check_log_entry('STDERR_LOG', url + '?filter=STREAM:STDERR', dcos_api_session)


def test_pod_logs(dcos_api_session):
    test_uuid = uuid.uuid4().hex

    pod_id = 'integration-test-pod-logs-{}'.format(test_uuid)

    pod_definition = {
        'id': '/{}'.format(pod_id),
        'scaling': {'kind': 'fixed', 'instances': 1},
        'environment': {'PING': 'PONG'},
        'containers': [
            {
                'name': 'sleep1',
                'exec': {'command': {'shell': 'echo $PING > foo;echo STDOUT_LOG;echo STDERR_LOG >&2;sleep 10000'}},
                'resources': {'cpus': 0.1, 'mem': 32},
                'healthcheck': {'command': {'shell': 'test $PING = `cat foo`'}}
            }
        ],
        'networks': [{'mode': 'host'}]
    }

    with dcos_api_session.marathon.deploy_pod_and_cleanup(pod_definition):
        url = get_task_url(dcos_api_session, pod_id)
        check_log_entry('STDOUT_LOG', url + '?filter=STREAM:STDOUT', dcos_api_session)
        check_log_entry('STDERR_LOG', url + '?filter=STREAM:STDERR', dcos_api_session)


@retrying.retry(wait_fixed=1000, stop_max_delay=3000)
def check_log_entry(log_line, url, dcos_api_session):
    response = dcos_api_session.get(url)
    check_response_ok(response, {})
    assert log_line in response.text, 'Missing {} in output {}'.format(log_line, response.text)


def get_task_url(dcos_api_session, task_name, stream=False):
    """ The function returns a logging URL for a given task

    :param dcos_api_session: dcos_api_session fixture
    :param task_name: task name
    :param stream: use range or stream endpoint
    :return: url to get the logs for a task
    """
    state_response = dcos_api_session.get('/mesos/state')
    check_response_ok(state_response, {})

    framework_id = None
    executor_id = None
    slave_id = None
    container_id = None

    state_response_json = state_response.json()
    assert 'frameworks' in state_response_json, 'Missing field `framework` in {}'.format(state_response_json)
    assert isinstance(state_response_json['frameworks'], list), '`framework` must be list. Got {}'.format(
        state_response_json)

    for framework in state_response_json['frameworks']:
        assert 'name' in framework, 'Missing field `name` in `frameworks`. Got {}'.format(state_response_json)
        # search for marathon framework
        if framework['name'] != 'marathon':
            continue

        assert 'tasks' in framework, 'Missing field `tasks`. Got {}'.format(state_response_json)
        assert isinstance(framework['tasks'], list), '`tasks` must be list. Got {}'.format(state_response_json)
        for task in framework['tasks']:
            assert 'id' in task, 'Missing field `id` in task. Got {}'.format(state_response_json)
            if not task['id'].startswith(task_name):
                continue

            assert 'framework_id' in task, 'Missing `framework_id` in task. Got {}'.format(state_response_json)
            assert 'executor_id' in task, 'Missing `executor_id` in task. Got {}'.format(state_response_json)
            assert 'id' in task, 'Missing `id` in task. Got {}'.format(state_response_json)
            assert 'slave_id' in task, 'Missing `slave_id` in task. Got {}'.format(state_response_json)

            framework_id = task['framework_id']
            # if task['executor_id'] is empty, we should use task['id']
            executor_id = task['executor_id']
            if not executor_id:
                executor_id = task['id']
            slave_id = task['slave_id']

            assert task['statuses'], 'Invalid field `statuses`. Got {}'.format(state_response_json)
            statuses = task['statuses']
            assert isinstance(statuses, list), 'Invalid field `statuses`. Got {}'.format(state_response_json)
            assert len(statuses) == 1, 'Must have only one status TASK_RUNNING. Got {}'.format(state_response_json)
            status = statuses[0]
            assert status['container_status'], 'Invalid field `container_status`. Got {}'.format(state_response_json)
            container_status = status['container_status']
            assert container_status['container_id'], 'Invalid field `container_id`. Got {}'.format(state_response_json)
            container_id_field = container_status['container_id']

            # traverse nested container_id fields
            container_ids = [container_id_field['value']]
            while 'parent' in container_id_field:
                container_id_field = container_id_field['parent']
                container_ids.append(container_id_field['value'])

            container_id = '.'.join(reversed(container_ids))
            assert container_id

    # validate all required fields
    assert slave_id, 'Missing slave_id'
    assert framework_id, 'Missing framework_id'
    assert executor_id, 'Missing executor_id'
    assert container_id, 'Missing container_id'

    endpoint_type = 'stream' if stream else 'range'
    return '/system/v1/agent/{}/logs/v1/{}/framework/{}/executor/{}/container/{}'.format(slave_id, endpoint_type,
                                                                                         framework_id, executor_id,
                                                                                         container_id)
