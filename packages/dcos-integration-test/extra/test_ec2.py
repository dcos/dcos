import contextlib
import copy
import logging
import os
import uuid

import boto3
import botocore
import pytest
import requests
import retrying


@contextlib.contextmanager
def _remove_env_vars(*env_vars):
    environ = dict(os.environ)

    for env_var in env_vars:
        try:
            del os.environ[env_var]
        except KeyError:
            pass

    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(environ)


def _delete_ec2_volume(name, timeout=300):
    """Delete an EC2 EBS volume by its "Name" tag

    Args:
        timeout: seconds to wait for volume to become available for deletion

    """
    @retrying.retry(wait_fixed=30 * 1000, stop_max_delay=timeout * 1000,
                    retry_on_exception=lambda exc: isinstance(exc, botocore.exceptions.ClientError))
    def _delete_volume(volume):
        volume.delete()  # Raises ClientError if the volume is still attached.

    def _get_current_aws_region():
        try:
            return requests.get('http://169.254.169.254/latest/meta-data/placement/availability-zone').text.strip()[:-1]
        except requests.RequestException as ex:
            logging.warning("Can't get AWS region from instance metadata: {}".format(ex))
            return None

    # Remove AWS environment variables to force boto to use IAM credentials.
    with _remove_env_vars('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'):
        volumes = list(boto3.session.Session(
            # We assume we're running these tests from a cluster node, so we
            # can assume the region for the instance on which we're running is
            # the same region in which any volumes were created.
            region_name=_get_current_aws_region(),
        ).resource('ec2').volumes.filter(Filters=[{'Name': 'tag:Name', 'Values': [name]}]))

    if len(volumes) == 0:
        raise Exception('no volumes found with name {}'.format(name))
    elif len(volumes) > 1:
        raise Exception('multiple volumes found with name {}'.format(name))
    volume = volumes[0]

    try:
        _delete_volume(volume)
    except retrying.RetryError as ex:
        raise Exception('Operation was not completed within {} seconds'.format(timeout)) from ex


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
        try:
            _delete_ec2_volume(test_label)
        except Exception as ex:
            raise Exception("Failed to clean up volume {}: {}".format(test_label, ex)) from ex
