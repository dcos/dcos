import copy
import logging
import uuid

import pytest

from test_helpers import expanded_config


@pytest.mark.supportedwindows
@pytest.mark.skipif(
    not (expanded_config['provider'] == 'aws' or expanded_config['platform'] == 'aws'),
    reason='Must be run in an AWS environment!')
def test_move_external_volume_to_new_agent(dcos_api_session):
    """Test that an external volume is successfully attached to a new agent.

    If the dcos_api_session has only one agent, the volume will be detached and
    reattached to the same agent.

    """
    hosts = dcos_api_session.slaves[0], dcos_api_session.slaves[-1]
    test_uuid = uuid.uuid4().hex
    test_label = 'integration-test-move-external-volume-{}'.format(test_uuid)
    mesos_volume_path = 'volume'
    docker_volume_path = '/volume'
    base_app = {
        'mem': 32,
        'cpus': 0.1,
        'instances': 1,
        'container': {
            'volumes': [{
                'mode': 'RW',
                'external': {
                    'name': test_label,
                    'provider': 'dvdi',
                    'options': {'dvdi/driver': 'rexray'}
                }
            }]
        }
    }

    write_app = copy.deepcopy(base_app)
    write_app.update({
        'id': '/{}/write'.format(test_label),
        'cmd': (
            # Check that the volume is empty.
            '[ $(ls -A {volume_path}/ | grep -v --line-regexp "lost+found" | wc -l) -eq 0 ] && '
            # Write the test UUID to a file.
            'echo "{test_uuid}" >> {volume_path}/test && '
            'while true; do sleep 1000; done'
        ).format(test_uuid=test_uuid, volume_path=mesos_volume_path),
        'constraints': [['hostname', 'LIKE', hosts[0]]],
    })
    write_app['container']['type'] = 'MESOS'
    write_app['container']['volumes'][0]['containerPath'] = mesos_volume_path
    write_app['container']['volumes'][0]['external']['size'] = 1

    read_app = copy.deepcopy(base_app)
    read_app.update({
        'id': '/{}/read'.format(test_label),
        'cmd': (
            # Diff the file and the UUID.
            'echo "{test_uuid}" | diff - {volume_path}/test && '
            'while true; do sleep 1000; done'
        ).format(test_uuid=test_uuid, volume_path=docker_volume_path),
        'constraints': [['hostname', 'LIKE', hosts[1]]],
    })
    read_app['container'].update({
        'type': 'DOCKER',
        'docker': {
            'image': 'busybox',
            'network': 'HOST',
        }
    })
    read_app['container']['volumes'][0]['containerPath'] = docker_volume_path

    # Volume operations can take several minutes.
    timeout = 600

    deploy_kwargs = {
        'check_health': False,
        # A volume might fail to attach because EC2. We can tolerate that and retry.
        'ignore_failed_tasks': True,
        'timeout': timeout
    }

    try:
        with dcos_api_session.marathon.deploy_and_cleanup(write_app, **deploy_kwargs):
            logging.info('Successfully wrote to volume')
        with dcos_api_session.marathon.deploy_and_cleanup(read_app, **deploy_kwargs):
            logging.info('Successfully read from volume')
    finally:
        logging.info('Deleting volume: ' + test_label)
        delete_cmd = \
            "/opt/mesosphere/bin/dcos-shell python " \
            "/opt/mesosphere/active/dcos-integration-test/util/delete_ec2_volume.py {}".format(test_label)
        delete_job = {
            'id': 'delete-volume-' + test_uuid,
            'run': {
                'cpus': .1,
                'mem': 128,
                'disk': 0,
                'cmd': delete_cmd}}
        try:
            # We use a metronome job to work around the `aws-deploy` integration tests where the master doesn't have
            # volume permissions so all volume actions need to be performed from the agents.
            dcos_api_session.metronome_one_off(delete_job, timeout=timeout)
        except Exception as ex:
            raise Exception('Failed to clean up volume {}: {}'.format(test_label, ex)) from ex
