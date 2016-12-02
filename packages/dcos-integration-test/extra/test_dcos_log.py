import json

import requests


def validate_json_entry(entry: dict):
    required_fields = set(['fields', 'cursor', 'monotonic_timestamp', 'realtime_timestamp'])

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


def test_log_text(cluster):
    for node in cluster.masters + cluster.all_slaves:
        response = cluster.logs.get('v1/range/?limit=10', node=node)
        check_response_ok(response, {'Content-Type': 'text/plain'})

        # expect 10 lines
        lines = filter(lambda x: x != '', response.content.decode().split('\n'))
        assert len(list(lines)) == 10, 'Expect 10 log entries. Got {}. All lines {}'.format(len(lines), lines)


def test_log_json(cluster):
    for node in cluster.masters + cluster.all_slaves:
        response = cluster.logs.get('v1/range/?limit=1', node=node, headers={'Accept': 'application/json'})
        check_response_ok(response, {'Content-Type': 'application/json'})
        validate_json_entry(response.json())


def test_log_server_sent_events(cluster):
    for node in cluster.masters + cluster.all_slaves:
        response = cluster.logs.get('v1/range/?limit=1', node=node, headers={'Accept': 'text/event-stream'})
        check_response_ok(response, {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache'})
        validate_sse_entry(response.content.decode())


def test_stream(cluster):
    for node in cluster.masters + cluster.all_slaves:
        response = cluster.logs.get('v1/stream/?skip_prev=1', node=node, stream=True,
                                    headers={'Accept': 'text/event-stream'})
        check_response_ok(response, {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache'})
        lines = response.iter_lines()
        sse_id = next(lines)
        assert sse_id, 'First line must be id. Got {}'.format(sse_id)
        data = next(lines).decode()
        validate_sse_entry(data)


def test_log_proxy(cluster):
    r = cluster.get('/mesos/master/slaves')
    check_response_ok(r, {})

    data = r.json()
    slaves_ids = sorted(x['id'] for x in data['slaves'] if x['hostname'] in cluster.all_slaves)

    for slave_id in slaves_ids:
        response = cluster.get('/system/v1/agent/{}/logs/v1/range/?skip_prev=10'.format(slave_id))
        check_response_ok(response, {'Content-Type': 'text/plain'})
        lines = filter(lambda x: x != '', response.content.decode().split('\n'))
        assert len(list(lines)) == 10, 'Expect 10 log entries. Got {}. All lines {}'.format(len(lines), lines)
