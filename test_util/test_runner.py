#!/usr/bin/env python3
"""Module for running integration_test.py inside of a remote cluster
Note: ssh_user must be able to use docker without sudo priveleges
"""
import logging
import tempfile
import time
from contextlib import contextmanager
from multiprocessing import Process
from os.path import join
from subprocess import CalledProcessError, TimeoutExpired, check_call

import pkg_resources

from pkgpanda.util import write_string

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
log = logging.getLogger(__name__)


@contextmanager
def remote_port_forwarding(tunnel, host_list, remote_key_path):
    """Forwards port 5000 from each host in in host_list to port 5000
    on tunnnel.host. This allows docker on hosts in host_list to pull from
    an insecure registry on tunnel host

    Args:
        tunnel: SSHTunnel instance connecting to host to be forwarded to
        host_list: list of host names to forward port 5000 from
        remote_key_path: arbitary path on tunnel.host for storing key
    """
    tunnel.write_to_remote(tunnel.ssh_key_path, remote_key_path)
    tunnel.remote_cmd(['chmod', '600', remote_key_path])
    cmd_list = [
            'ssh', '-i', remote_key_path,
            '-l', tunnel.ssh_user,
            '-T', '-n', '-N',
            '-oBatchMode=yes',
            '-oGatewayPorts=yes',
            '-oStrictHostKeyChecking=no',
            '-oUserKnownHostsFile=/dev/null',
            '-oExitOnForwardFailure=yes',
            '-R', '5000:127.0.0.1:5000']
    p_list = []
    log.info('Starting proxy of port 5000 from {} to {}'.format(host_list, tunnel.host))
    for host in host_list:
        host_cmd_list = cmd_list + [host]
        p = Process(target=tunnel.remote_cmd, args=(host_cmd_list,))
        p.start()
        p_list.append(p)
    yield
    for p in p_list:
        p.terminate()


def pkg_filename(relative_path):
    return pkg_resources.resource_filename(__name__, relative_path)


def prepare_test_registry(tunnel, test_dir):
    """Transfer resources and issues commands on host to build test app,
    host it on a docker registry, and prepare the integration_test container

    Args:
        tunnel: SSHTunnel instance
        test_dir (str): path to be used for landing docker archives
    """
    test_server_docker = pkg_filename('docker/test_server/Dockerfile')
    test_server_script = pkg_filename('docker/test_server/test_server.py')
    log.info('Setting up integration_test.py to run on ' + tunnel.host)

    tunnel.remote_cmd(['mkdir', '-p', join(test_dir, 'test_server')])
    tunnel.write_to_remote(test_server_docker, join(test_dir, 'test_server/Dockerfile'))
    tunnel.write_to_remote(test_server_script, join(test_dir, 'test_server/test_server.py'))
    log.info('Starting insecure registry on test host')
    try:
        log.debug('Attempt to replace a previously setup registry')
        tunnel.remote_cmd(['docker', 'kill', 'registry'])
        tunnel.remote_cmd(['docker', 'rm', 'registry'])
    except CalledProcessError:
        log.debug('No previous registry to kill or delete')
    tunnel.remote_cmd([
        'docker', 'run', '-d', '-p', '5000:5000', '--restart=always', '--name',
        'registry', 'registry:2'])
    log.info('Building test_server Docker image on test host')
    tunnel.remote_cmd([
        'cd', join(test_dir, 'test_server'), '&&', 'docker', 'build', '-t',
        '127.0.0.1:5000/test_server', '.'])
    log.info('Pushing built test server to insecure registry')
    tunnel.remote_cmd(['docker', 'push', '127.0.0.1:5000/test_server'])
    log.debug('Cleaning up test_server files')
    tunnel.remote_cmd(['rm', '-rf', join(test_dir, 'test_server')])


def integration_test(
        tunnel, test_dir,
        dcos_dns, master_list, agent_list, public_agent_list,
        variant, test_dns_search, provider, ci_flags, timeout=None,
        aws_access_key_id='', aws_secret_access_key='', region='', add_env=None):
    """Runs integration test on host

    Args:
        test_dir: string representing host where integration_test.py exists on test_host
        dcos_dns: string representing IP of DCOS DNS host
        master_list: string of comma separated master addresses
        agent_list: string of comma separated agent addresses
        variant: 'ee' or 'default'
        test_dns_search: if set to True, test for deployed mesos DNS app
        ci_flags: optional additional string to be passed to test
        provider: (str) either onprem, aws, or azure
        # The following variables correspond to currently disabled tests
        aws_access_key_id: needed for REXRAY tests
        aws_secret_access_key: needed for REXRAY tests
        region: string indicating AWS region in which cluster is running
        add_env: a python dict with any number of key=value assignments to be passed to
            the test environment
    """
    test_script = pkg_filename('integration_test.py')
    pytest_docker = pkg_filename('docker/py.test/Dockerfile')

    dns_search = 'true' if test_dns_search else 'false'
    test_env = [
        'DCOS_DNS_ADDRESS=http://'+dcos_dns,
        'MASTER_HOSTS='+','.join(master_list),
        'PUBLIC_MASTER_HOSTS='+','.join(master_list),
        'SLAVE_HOSTS='+','.join(agent_list),
        'PUBLIC_SLAVE_HOSTS='+','.join(public_agent_list),
        'REGISTRY_HOST=127.0.0.1',
        'DCOS_VARIANT='+variant,
        'DCOS_PROVIDER='+provider,
        'DNS_SEARCH='+dns_search,
        'AWS_ACCESS_KEY_ID='+aws_access_key_id,
        'AWS_SECRET_ACCESS_KEY='+aws_secret_access_key,
        'AWS_REGION='+region]
    if add_env:
        for key, value in add_env.items():
            extra_env = key + '=' + value
            test_env.append(extra_env)
    test_env = ['export '+e+'\n' for e in test_env]
    test_env = ''.join(test_env)
    test_cmd = 'py.test -vv ' + ci_flags + ' /integration_test.py'

    log.info('Building py.test image')
    # Make a clean docker context
    temp_dir = tempfile.mkdtemp()
    cmd_script = """
#!/bin/bash
set -euo pipefail; set -x
{test_env}
{test_cmd}
""".format(test_env=test_env, test_cmd=test_cmd)
    write_string(join(temp_dir, 'test_wrapper.sh'), cmd_script)
    check_call(['cp', test_script, join(temp_dir, 'integration_test.py')])
    check_call(['cp', pytest_docker, join(temp_dir, 'Dockerfile')])
    check_call(['docker', 'build', '-t', 'py.test', temp_dir])

    log.info('Exporting py.test image')
    pytest_image_tar = 'DCOS_integration_test.tar'
    check_call(['docker', 'save', '-o', join(temp_dir, pytest_image_tar), 'py.test'])

    log.info('Transferring py.test image')
    tunnel.write_to_remote(join(temp_dir, pytest_image_tar), join(test_dir, pytest_image_tar))
    log.info('Loading py.test image on remote host')
    tunnel.remote_cmd(['docker', 'load', '-i', join(test_dir, pytest_image_tar)])

    test_container_name = 'int_test_' + str(int(time.time()))
    docker_cmd = ['docker', 'run', '--net=host', '--name='+test_container_name, 'py.test']
    try:
        with remote_port_forwarding(tunnel, agent_list+public_agent_list, join(test_dir, 'ssh_key')):
            log.info('Running integration test...')
            try:
                tunnel.remote_cmd(docker_cmd, timeout=timeout)
            except CalledProcessError:
                log.exception('Test failed!')
                if ci_flags:
                    return False
                raise
        log.info('Successful test run!')
    except TimeoutExpired:
        log.error('Test failed due to timing out after {} seconds'.format(timeout))
        raise
    finally:
        get_logs_cmd = ['docker', 'logs', test_container_name]
        test_log = tunnel.remote_cmd(get_logs_cmd)
        log_file = 'integration_test.log'
        with open(log_file, 'wb') as fh:
            fh.write(test_log)
        log.info('Logs from test container can be found in '+log_file)

    return True
