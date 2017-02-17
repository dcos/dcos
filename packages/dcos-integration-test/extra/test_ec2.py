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

from test_util.helpers import retry_boto_rate_limits


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


@pytest.mark.ccm
def test_move_external_volume_to_new_agent(dcos_api_session):
    """Test that an external volume is successfully attached to a new agent.

    If the dcos_api_session has only one agent, the volume will be detached and
    reattached to the same agent.

    """

    # Volume operations on EC2 can take a really long time.
    # We set the timeout to 10 mins to account for this.
    # For now, we expect no volume operation to take more than 10 minutes.
    timeout = 600

    @retry_boto_rate_limits
    def get_volume(volume_label):
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
            ).resource('ec2').volumes.filter(Filters=[{'Name': 'tag:Name', 'Values': [volume_label]}]))

        if len(volumes) == 0:
            raise Exception('no volumes found with label {}'.format(volume_label))
        elif len(volumes) > 1:
            raise Exception('multiple volumes found with label {}'.format(volume_label))
        return volumes[0]

    @retry_boto_rate_limits
    def delete_volume(volume_label):
        """Delete the volume corresponding to volume_label."""
        @retrying.retry(wait_fixed=30 * 1000, stop_max_delay=timeout * 1000,
                        retry_on_exception=lambda exc: isinstance(exc, botocore.exceptions.ClientError))
        def _delete_vol(volume):
            volume.delete()  # Raises ClientError if the volume is still attached.

        volume = get_volume(volume_label)
        try:
            _delete_vol(volume)
        except retrying.RetryError as ex:
            raise Exception('Could not delete volume within {} seconds'.format(timeout)) from ex
        
    @retry_boto_rate_limits
    def wait_for_volume_state(volume_label, state):
        """Wait for the volume corresponding to volume_label to report state."""
        delay = 10
        @retrying.retry(wait_fixed=delay * 1000, stop_max_delay=timeout * 1000,
                        retry_on_exception=lambda exc: isinstance(exc, botocore.exceptions.ClientError),
                        retry_on_result=lambda res: res is False)
        def _wait_for_state(state):
            volume = get_volume(volume_label)
            if volume.state == state:
                logging.info('volume state is {}'.format(state))
                return True
            else:
                logging.info('volume state is {} != {}, waiting 10s'.format(volume.state, state))
                return False

        try:
            _wait_for_state(state)
        except retrying.RetryError as ex:
            raise Exception('Waited {} seconds for volume to become {} before giving up'.format(timeout, state))

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

    deploy_kwargs = {
        'check_health': False,
        # A volume might fail to attach because EC2. We can tolerate that and retry.
        'ignore_failed_tasks': True,
        'timeout': timeout
    }

    try:
        with dcos_api_session.marathon.deploy_and_cleanup(write_app, **deploy_kwargs):
            logging.info('Successfully wrote to volume')
        wait_for_volume_state(test_label, "available")
        with dcos_api_session.marathon.deploy_and_cleanup(read_app, **deploy_kwargs):
            logging.info('Successfully read from volume')
        wait_for_volume_state(test_label, "available")
    finally:
        logging.info('Deleting volume: ' + test_label)
        try:
            delete_volume(test_label)
        except Exception as ex:
            raise Exception('Failed to clean up volume {}: {}'.format(test_label, ex)) from ex
