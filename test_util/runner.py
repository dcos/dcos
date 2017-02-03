#!/usr/bin/env python3
"""Module for running integration tests inside of a remote cluster
Note: ssh_user must be able to use docker without sudo privileges
"""
import logging
import sys
from subprocess import CalledProcessError

log = logging.getLogger(__name__)


def integration_test(
        tunnel,
        dcos_dns, master_list, agent_list, public_agent_list,
        aws_access_key_id='', aws_secret_access_key='', region='',
        test_cmd='py.test'):
    """Runs integration test on host

    Args:
        dcos_dns: string representing IP of DCOS DNS host
        master_list: string of comma separated master addresses
        agent_list: string of comma separated agent addresses
    Optional args:
        aws_access_key_id: needed for REXRAY tests
        aws_secret_access_key: needed for REXRAY tests
        region: string indicating AWS region in which cluster is running
        test_cmd: string to be passed to dcos-shell using
            /opt/mesosphere/active/dcos-integration-test as the working dir

    Returns:
        exit code from last test command

    """
    required_test_env = [
        'DCOS_DNS_ADDRESS=http://' + dcos_dns,
        'MASTER_HOSTS=' + ','.join(master_list),
        'PUBLIC_MASTER_HOSTS=' + ','.join(master_list),
        'SLAVE_HOSTS=' + ','.join(agent_list),
        'PUBLIC_SLAVE_HOSTS=' + ','.join(public_agent_list),
        'AWS_ACCESS_KEY_ID=' + aws_access_key_id,
        'AWS_SECRET_ACCESS_KEY=' + aws_secret_access_key,
        'AWS_REGION=' + region]

    pytest_cmd = """ "source /opt/mesosphere/environment.export &&
cd /opt/mesosphere/active/dcos-integration-test &&
{env} {cmd}" """.format(env=' '.join(required_test_env), cmd=test_cmd)

    log.info('Running integration test...')
    try:
        tunnel.remote_cmd(['bash', '-c', pytest_cmd], stdout=sys.stdout.buffer)
    except CalledProcessError as e:
        return e.returncode
    return 0
