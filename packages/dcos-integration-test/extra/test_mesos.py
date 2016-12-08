import logging
import uuid

import requests

from test_util.marathon import get_test_app


def test_if_marathon_app_can_be_debugged(cluster):
    def post(url, headers, data, stream=False):
        r = requests.post(url, headers=headers, json=data, stream=stream)
        logging.info(
            'Got %s with POST request to %s with headers %s and data %s.',
            r.status_code,
            url,
            headers,
            data
        )
        assert r.status_code == 200

    def find_container_id(state, app_id):
        if 'frameworks' in state:
            for framework in state['frameworks']:
                # TODO: Skip anything that's not Marathon
                if 'tasks' in framework:
                    for task in framework['tasks']:
                        if 'id' in task and app_id in task['id']:
                            if 'statuses' in task and 'container_status' in task['statuses'][0]:
                                if 'container_id' in task['statuses'][0]['container_status']:
                                    container_status = task['statuses'][0]['container_status']
                                    if 'container_id' in container_status:
                                        if 'value' in container_status['container_id']:
                                            return container_status['container_id']['value']

    def find_agent_id(state, app_id):
        if 'frameworks' in state:
            for framework in state['frameworks']:
                # TODO: Skip anything that's not Marathon
                if 'tasks' in framework:
                    for task in framework['tasks']:
                        if 'id' in task and app_id in task['id']:
                            if 'slave_id' in task:
                                return task['slave_id']

    def find_agent_hostname(state, agent_id):
        if 'slaves' in state:
            for agent in state['slaves']:
                if 'id' in agent and agent['id'] == agent_id and 'hostname' in agent:
                    return agent['hostname']

    # Launch a basic marathon app (no image), so we can debug into it!
    app, test_uuid = get_test_app()
    test_app_id = 'integration-test-{}'.format(test_uuid)
    cluster.marathon.deploy_app(app)

    # Find the agent_id and container_id from master state
    master_state_url = 'http://{}:{}/state'.format(cluster.masters[0], 5050)
    r = requests.get(master_state_url)
    logging.info('Got %s with request for %s. Response: \n%s', r.status_code, master_state_url, r.text)
    assert r.status_code == 200
    state = r.json()

    container_id = find_container_id(state, test_app_id)
    agent_id = find_agent_id(state, test_app_id)
    agent_hostname = find_agent_hostname(state, agent_id)
    agent_v1_url = 'http://{}:{}/api/v1'.format(agent_hostname, 5051)
    logging.info('Located %s with containerID %s on agent %s', test_app_id, container_id, agent_hostname)

    # Attach to output stream of container
    container_id_data = {'value': '%s' % container_id}
    attach_out_data = {'type': 'ATTACH_CONTAINER_OUTPUT', 'attach_container_output': {}}
    attach_out_data['attach_container_output']['container_id'] = container_id_data
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json+recordio',
        'connection': 'keep-alive'
    }
    logging.info('Making POST call to %s with: %s', agent_v1_url, attach_out_data)
    r = post(agent_v1_url, headers, attach_out_data, stream=True)
    # TODO: verify some output
    r.close()

    # Prepare nested container id
    nested_container_id = {'value': 'debug-%s' % str(uuid.uuid4())}
    nested_container_id['parent'] = container_id_data

    # Launch debug session and attach to output stream of debug container
    lncs_data = {'type': 'LAUNCH_NESTED_CONTAINER_SESSION', 'launch_nested_container_session': {}}
    lncs_data['launch_nested_container_session']['command'] = {'value': 'echo echo'}
    lncs_data['launch_nested_container_session']['container_id'] = nested_container_id
    logging.info('Creating nested container session: %s', nested_container_id)
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json+recordio',
        'connection': 'keep-alive'
    }
    r = post(agent_v1_url, headers, lncs_data, stream=True)
    # TODO: verify more of the response contents?
    # TODO: verify some output
    r.close()

    # Attach to input stream of debug container
    attach_in_data = {'type': 'ATTACH_CONTAINER_INPUT', 'attach_container_input': {}}
    attach_in_data['attach_container_input']['type'] = 'CONTAINER_ID'
    attach_in_data['attach_container_input']['container_id'] = nested_container_id
    # r = post(agent_v1_url, attach_in_data)
    # TODO: input something and verify it
    # r.close()

    cluster.marathon.destroy_app(test_app_id)
