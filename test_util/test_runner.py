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
    client_cert = pkg_filename('certs/client.cert')
    client_key = pkg_filename('certs/client.key')
    root_ca = pkg_filename('certs/123.1.1.1:5000.crt')
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

    # Put certs in a temp dir we'll use to tar them up and scp to boostrapper later
    certs_temp_dir = tempfile.mkdtemp()
    check_call(['cp', client_cert, join(certs_temp_dir, 'client.cert')])
    check_call(['cp', client_key, join(certs_temp_dir, 'client.key')])
    check_call(['cp', root_ca, join(certs_temp_dir, '123.1.1.1:5000.crt')])

    log.info('Tar-ing certs dir')
    certs_tarball = join(certs_temp_dir, 'certs.tgz')
    check_call(['tar', 'czf', certs_tarball, 'certs'], cwd=join(certs_temp_dir, 'include'))

    log.info("Certs Tarball: {}".format(certs_tarball))
    # Transfer certs to bootstrap host
    cert_transfer_path = join(test_dir, 'certs.tgz')
    tunnel.write_to_remote(certs_tarball, cert_transfer_path)

    log.info('Setting up SSH key on bootstrap host for daisy-chain-ing')
    remote_key_path = join(test_dir, 'test_ssh_key')
    tunnel.write_to_remote(tunnel.ssh_key_path, remote_key_path)
    tunnel.remote_cmd(['chmod', '600', remote_key_path])

    docker_conf_chain = (
        ['docker', 'version'],  # checks that docker is available w/o sudo
        ['tar', 'xzf', cert_transfer_path, '-C', test_dir],
        ['sudo', 'cp', '-R', join(test_dir, 'certs'), '/etc/docker/certs.d/'])

    for cmd in docker_conf_chain:
        tunnel.remote_cmd(cmd)
    for agent in agent_list:
        log.info('Adding self-signed certs to:  ' + agent)
        target = "{}@{}".format(tunnel.ssh_user, agent)
        target_scp = "{}:{}".format(target, cert_transfer_path)
        ssh_opts = ['-oStrictHostKeyChecking=no', '-oUserKnownHostsFile=/dev/null']
        scp_cmd = ['/usr/bin/scp', '-i', remote_key_path] + ssh_opts
        remote_scp = scp_cmd + [cert_transfer_path, target_scp]
        tunnel.remote_cmd(remote_scp)
        chain_prefix = ['/usr/bin/ssh', '-tt', '-i', remote_key_path] + ssh_opts + [target]
        for cmd in docker_conf_chain:
            tunnel.remote_cmd(chain_prefix+cmd)

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
