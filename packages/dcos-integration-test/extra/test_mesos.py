import json
import logging
import uuid

import pytest

import retrying

import test_helpers
from dcos_test_utils import marathon, recordio


# Creates and yields the initial ATTACH_CONTAINER_INPUT message, then a data message,
# then an empty data chunk to indicate end-of-stream.
def input_streamer(nested_container_id):
    encoder = recordio.Encoder(lambda s: bytes(json.dumps(s, ensure_ascii=False), "UTF-8"))
    message = {
        'type': 'ATTACH_CONTAINER_INPUT',
        'attach_container_input': {
            'type': 'CONTAINER_ID',
            'container_id': nested_container_id}}
    yield encoder.encode(message)

    message['attach_container_input'] = {
        'type': 'PROCESS_IO',
        'process_io': {
            'type': 'DATA',
            'data': {'type': 'STDIN', 'data': 'meow'}}}
    yield encoder.encode(message)

    # Place an empty string to indicate EOF to the server and push
    # 'None' to our queue to indicate that we are done processing input.
    message['attach_container_input']['process_io']['data']['data'] = ''
    yield encoder.encode(message)


def test_if_marathon_app_can_be_debugged(dcos_api_session):
    # Launch a basic marathon app (no image), so we can debug into it!
    # Cannot use deploy_and_cleanup because we must attach to a running app/task/container.
    app, test_uuid = test_helpers.marathon_test_app()
    app_id = 'integration-test-{}'.format(test_uuid)
    with dcos_api_session.marathon.deploy_and_cleanup(app):
        # Fetch the mesos master state once the task is running
        master_ip = dcos_api_session.masters[0]
        r = dcos_api_session.get('/state', host=master_ip, port=5050)
        assert r.status_code == 200
        state = r.json()

        # Find the agent_id and container_id from master state
        container_id = None
        agent_id = None
        for framework in state['frameworks']:
            for task in framework['tasks']:
                if app_id in task['id']:
                    container_id = task['statuses'][0]['container_status']['container_id']['value']
                    agent_id = task['slave_id']
        assert container_id is not None, 'Container ID not found for instance of app_id {}'.format(app_id)
        assert agent_id is not None, 'Agent ID not found for instance of app_id {}'.format(app_id)

        # Find hostname and URL from agent_id
        agent_hostname = None
        for agent in state['slaves']:
            if agent['id'] == agent_id:
                agent_hostname = agent['hostname']
        assert agent_hostname is not None, 'Agent hostname not found for agent_id {}'.format(agent_id)
        logging.debug('Located %s with containerID %s on agent %s', app_id, container_id, agent_hostname)

        def _post_agent(url, headers, json=None, data=None, stream=False):
            r = dcos_api_session.post(
                url,
                host=agent_hostname,
                port=5051,
                headers=headers,
                json=json,
                data=data,
                stream=stream)
            assert r.status_code == 200
            return r

        # Prepare nested container id data
        nested_container_id = {
            'value': 'debug-%s' % str(uuid.uuid4()),
            'parent': {'value': '%s' % container_id}}

        # Launch debug session and attach to output stream of debug container
        output_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/recordio',
            'Message-Accept': 'application/json'
        }
        lncs_data = {
            'type': 'LAUNCH_NESTED_CONTAINER_SESSION',
            'launch_nested_container_session': {
                'command': {'value': 'cat'},
                'container_id': nested_container_id}}
        launch_output = _post_agent('/api/v1', output_headers, json=lncs_data, stream=True)

        # Attach to output stream of nested container
        attach_out_data = {
            'type': 'ATTACH_CONTAINER_OUTPUT',
            'attach_container_output': {'container_id': nested_container_id}}
        attached_output = _post_agent('/api/v1', output_headers, json=attach_out_data, stream=True)

        # Attach to input stream of debug container and stream a message
        input_headers = {
            'Content-Type': 'application/recordio',
            'Message-Content-Type': 'application/json',
            'Accept': 'application/json',
            'Transfer-Encoding': 'chunked'
        }
        _post_agent('/api/v1', input_headers, data=input_streamer(nested_container_id))

        # Verify the streamed output from the launch session
        meowed = False
        decoder = recordio.Decoder(lambda s: json.loads(s.decode("UTF-8")))
        for chunk in launch_output.iter_content():
            for r in decoder.decode(chunk):
                if r['type'] == 'DATA':
                    logging.debug('Extracted data chunk: %s', r['data'])
                    assert r['data']['data'] == 'meow', 'Output did not match expected'
                    meowed = True
        assert meowed, 'Read launch output without seeing meow.'

        meowed = False
        # Verify the message from the attached output stream
        for chunk in attached_output.iter_content():
            for r in decoder.decode(chunk):
                if r['type'] == 'DATA':
                    logging.debug('Extracted data chunk: %s', r['data'])
                    assert r['data']['data'] == 'meow', 'Output did not match expected'
                    meowed = True
        assert meowed, 'Read output stream without seeing meow.'


def test_files_api(dcos_api_session):
    app, test_uuid = test_helpers.marathon_test_app()

    with dcos_api_session.marathon.deploy_and_cleanup(app):
        marathon_framework_id = dcos_api_session.marathon.get('/v2/info').json()['frameworkId']
        app_task = dcos_api_session.marathon.get('/v2/apps/{}/tasks'.format(app['id'])).json()['tasks'][0]

        for required_sandbox_file in ('stdout', 'stderr'):
            content = dcos_api_session.mesos_sandbox_file(
                app_task['slaveId'], marathon_framework_id, app_task['id'], required_sandbox_file)

            assert content, 'File {} should not be empty'.format(required_sandbox_file)


def test_if_ucr_app_runs_in_new_pid_namespace(dcos_api_session):
    # We run a marathon app instead of a metronome job because metronome
    # doesn't support running docker images with the UCR. We need this
    # functionality in order to test that the pid namespace isolator
    # is functioning correctly.
    app, test_uuid = test_helpers.marathon_test_app(container_type=marathon.Container.MESOS)

    ps_output_file = 'ps_output'
    app['cmd'] = 'ps ax -o pid= > {}; sleep 1000'.format(ps_output_file)

    with dcos_api_session.marathon.deploy_and_cleanup(app, check_health=False):
        marathon_framework_id = dcos_api_session.marathon.get('/v2/info').json()['frameworkId']
        app_task = dcos_api_session.marathon.get('/v2/apps/{}/tasks'.format(app['id'])).json()['tasks'][0]

        # There is a short delay between the `app_task` starting and it writing
        # its output to the `pd_output_file`. Because of this, we wait up to 10
        # seconds for this file to appear before throwing an exception.
        @retrying.retry(wait_fixed=1000, stop_max_delay=10000)
        def get_ps_output():
            return dcos_api_session.mesos_sandbox_file(
                app_task['slaveId'], marathon_framework_id, app_task['id'], ps_output_file)

        assert len(get_ps_output().split()) <= 4, 'UCR app has more than 4 processes running in its pid namespace'


def get_region_zone(domain):
    assert isinstance(domain, dict), 'input must be dict'

    assert 'fault_domain' in domain, 'fault_domain is missing. {}'.format(domain)

    # check region set correctly
    assert 'region' in domain['fault_domain'], 'missing region. {}'.format(domain)
    assert 'name' in domain['fault_domain']['region'], 'missing region. {}'.format(domain)
    region = domain['fault_domain']['region']['name']

    # check zone set correctly
    assert 'zone' in domain['fault_domain'], 'missing zone. {}'.format(domain)
    assert 'name' in domain['fault_domain']['zone'], 'missing zone. {}'.format(domain)
    zone = domain['fault_domain']['zone']['name']

    return region, zone


@pytest.mark.skipif(
    test_helpers.expanded_config['fault_domain_enabled'] == 'false',
    reason='fault domain is not set')
def test_fault_domain(dcos_api_session):
    master_ip = dcos_api_session.masters[0]
    r = dcos_api_session.get('/state', host=master_ip, port=5050)
    assert r.status_code == 200
    state = r.json()

    # check flags and get the domain parameters mesos master was started with.
    assert 'flags' in state, 'missing flags in state json'
    assert 'domain' in state['flags'], 'missing domain in state json flags'
    cli_flag = json.loads(state['flags']['domain'])
    expected_region, expected_zone = get_region_zone(cli_flag)

    # check master top level keys
    assert 'leader_info' in state, 'leader_info is missing in state json'
    assert 'domain' in state['leader_info'], 'domain is missing in state json'
    leader_region, leader_zone = get_region_zone(state['leader_info']['domain'])

    assert leader_region == expected_region, 'expect region {}. Got {}'.format(expected_region, leader_region)
    assert leader_zone == expected_zone, 'expect zone {}. Got {}'.format(expected_zone, leader_zone)

    for agent in state['slaves']:
        assert 'domain' in agent, 'missing domain field for agent. {}'.format(agent)
        agent_region, agent_zone = get_region_zone(agent['domain'])

        assert agent_region == expected_region, 'expect region {}. Got {}'.format(expected_region, agent_region)

        # agent_zone might be different on agents, so we just make sure it's a sane value
        assert agent_zone, 'agent_zone cannot be empty'
