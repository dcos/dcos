import copy
import logging
import uuid

import pytest


@pytest.mark.ccm
def test_move_external_volume_to_new_agent(cluster):
    """Test that an external volume is successfully attached to a new agent.

    If the cluster has only one agent, the volume will be detached and
    reattached to the same agent.

    """
    hosts = cluster.slaves[0], cluster.slaves[-1]
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

    deploy_kwargs = {
        'check_health': False,
        # A volume might fail to attach because EC2. We can tolerate that and retry.
        'ignore_failed_tasks': True,
    }

    try:
        cluster.deploy_marathon_app(write_app, **deploy_kwargs)
        cluster.destroy_marathon_app(write_app['id'])

        cluster.deploy_marathon_app(read_app, **deploy_kwargs)
        cluster.destroy_marathon_app(read_app['id'])
    finally:
        logging.info('Deleting volume: ' + test_label)
        delete_cmd = """#!/bin/bash
source /opt/mesosphere/environment.export
python /opt/mesosphere/active/dcos-integration-test/delete_ec2_volume.py {}
""".format(test_label)
        delete_job = {
            'id': 'delete-volume-' + test_uuid,
            'run': {
                'cpus': .1,
                'mem': 128,
                'disk': 0,
                'cmd': delete_cmd}}
        try:
            cluster.metronome_one_off(delete_job)
        except Exception as ex:
            raise Exception('Failed to clean up volume {}: {}'.format(test_label, ex)) from ex
