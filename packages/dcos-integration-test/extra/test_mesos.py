import json
import logging
import uuid

import requests

from test_util.marathon import get_test_app
from test_util.recordio import Decoder, Encoder


# Wrapper to post, log, and validate return status
def post(url, headers, json=None, data=None, stream=False):
    r = requests.post(url, headers=headers, json=json, data=data, stream=stream)
    logging.info(
        'Got %s with POST request to %s with headers %s and json data %s.',
        r.status_code,
        url,
        headers,
        json
    )
    assert r.status_code == 200
    return r


# Creates and yields the initial ATTACH_CONTAINER_INPUT message, then a data message,
# then an empty data chunk to indicate end-of-stream.
def input_streamer(nested_container_id):
    encoder = Encoder(lambda s: bytes(json.dumps(s, ensure_ascii=False), "UTF-8"))
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
    app, test_uuid = get_test_app()
    app_id = 'integration-test-{}'.format(test_uuid)
    with dcos_api_session.marathon.deploy_and_cleanup(app):
        # Fetch the mesos master state once the task is running
        master_state_url = 'http://{}:{}/state'.format(dcos_api_session.masters[0], 5050)
        r = requests.get(master_state_url)
        logging.debug('Got %s with request for %s. Response: \n%s', r.status_code, master_state_url, r.text)
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
        agent_v1_url = 'http://{}:{}/api/v1'.format(agent_hostname, 5051)
        logging.debug('Located %s with containerID %s on agent %s', app_id, container_id, agent_hostname)

        # Prepare nested container id data
        nested_container_id = {
            'value': 'debug-%s' % str(uuid.uuid4()),
            'parent': {'value': '%s' % container_id}}

        # Launch debug session and attach to output stream of debug container
        output_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json+recordio',
            'Connection': 'keep-alive'
        }
        lncs_data = {
            'type': 'LAUNCH_NESTED_CONTAINER_SESSION',
            'launch_nested_container_session': {
                'command': {'value': 'cat'},
                'container_id': nested_container_id}}
        launch_output = post(agent_v1_url, output_headers, json=lncs_data, stream=True)

        # Attach to output stream of nested container
        attach_out_data = {
            'type': 'ATTACH_CONTAINER_OUTPUT',
            'attach_container_output': {'container_id': nested_container_id}}
        attached_output = post(agent_v1_url, output_headers, json=attach_out_data, stream=True)

        # Attach to input stream of debug container and stream a message
        input_headers = {
            'Content-Type': 'application/json+recordio',
            'Accept': 'application/json',
            'Connection': 'keep-alive',
            'Transfer-Encoding': 'chunked'
        }
        post(agent_v1_url, input_headers, data=input_streamer(nested_container_id))

        # Verify the streamed output from the launch session
        meowed = False
        decoder = Decoder(lambda s: json.loads(s.decode("UTF-8")))
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
