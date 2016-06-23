#!/usr/bin/env python3
"""Module for running integration_test.py inside of a remote cluster
Note: ssh_user must be able to use docker without sudo priveleges
"""
import logging
import tempfile
import time
from os.path import join
from subprocess import CalledProcessError, TimeoutExpired, check_call

import pkg_resources

from pkgpanda.util import write_string

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
log = logging.getLogger(__name__)


def pkg_filename(relative_path):
    return pkg_resources.resource_filename(__name__, relative_path)


def distribute_registry_certs(tunnel, agent_list, test_dir):
    """Copies certs to all agents in tests so that they
    may pull test server apppication from test_registy
    """
    client_certs = pkg_filename('certs')
    remote_tar_path = join(test_dir, 'certs.tgz')
    with tempfile.TemporaryDirectory() as d:
        log.info('Bundling and transferring certs')
        local_tar_path = join(d, 'certs.tgz')
        check_call(['tar', 'czf', local_tar_path, '-C', client_certs, '.'])
        tunnel.write_to_remote(local_tar_path, remote_tar_path)
    # setup for file transfer daisy chain
    remote_key_path = join(test_dir, 'test_ssh_key')
    tunnel.write_to_remote(tunnel.ssh_key_path, remote_key_path)
    tunnel.remote_cmd(['chmod', '600', remote_key_path])

    certs_dir = '/etc/docker/certs.d/123.1.1.1:5000'
    docker_conf_chain = (
        ['sudo', 'mkdir', '-p', certs_dir],
        ['sudo', 'tar', '-xzf', remote_tar_path, '-C', certs_dir])
    log.info('Reconfiguring dockerd on test host')
    for cmd in docker_conf_chain:
        tunnel.remote_cmd(cmd)
    for agent in agent_list:
        target = "{}@{}".format(tunnel.ssh_user, agent)
        target_scp = "{}:{}".format(target, remote_tar_path)
        ssh_opts = ['-oStrictHostKeyChecking=no', '-oUserKnownHostsFile=/dev/null']
        scp_cmd = ['/usr/bin/scp', '-i', remote_key_path] + ssh_opts
        remote_scp = scp_cmd + [remote_tar_path, target_scp]
        log.info('Transfering certs to host: ' + agent)
        tunnel.remote_cmd(remote_scp)
        chain_prefix = ['/usr/bin/ssh', '-tt', '-i', remote_key_path] + ssh_opts + [target]
        for cmd in docker_conf_chain:
            log.info('Unpacking certs on agent: '+agent)
            tunnel.remote_cmd(chain_prefix+cmd)


def integration_test(
        tunnel, test_dir,
        dcos_dns, master_list, agent_list, public_agent_list,
        test_dns_search, provider, ci_flags, timeout=None,
        aws_access_key_id='', aws_secret_access_key='', region='', add_env=None):
    """Runs integration test on host

    Args:
        test_dir: string representing host where integration_test.py exists on test_host
        dcos_dns: string representing IP of DCOS DNS host
        master_list: string of comma separated master addresses
        agent_list: string of comma separated agent addresses
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
    test_server = pkg_filename('docker/test_server/test_server.py')
    test_server_docker = pkg_filename('docker/test_server/Dockerfile')

    dns_search = 'true' if test_dns_search else 'false'
    test_env = [
        'DCOS_DNS_ADDRESS=http://'+dcos_dns,
        'MASTER_HOSTS='+','.join(master_list),
        'PUBLIC_MASTER_HOSTS='+','.join(master_list),
        'SLAVE_HOSTS='+','.join(agent_list),
        'PUBLIC_SLAVE_HOSTS='+','.join(public_agent_list),
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
    check_call(['cp', test_server, join(temp_dir, 'test_server.py')])
    check_call(['cp', test_server_docker, join(temp_dir, 'test_server_Dockerfile')])
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
        log.info('Running integration test...')
        tunnel.remote_cmd(docker_cmd, timeout=timeout)
        log.info('Successful test run!')
    except CalledProcessError:
        log.exception('Test failed!')
        if ci_flags:
            return False
        raise
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
