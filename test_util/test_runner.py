#!/usr/bin/env python3
"""Module for running integration_test.py inside of a remote cluster
Note: ssh_user must be able to use docker without sudo priveleges
"""
import logging
import shutil
import tempfile
import time
from os.path import join
from subprocess import CalledProcessError, TimeoutExpired, check_call

import pkg_resources

from pkgpanda.util import write_string

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
log = logging.getLogger(__name__)

REGISTRY_DOCKERFILE = """FROM registry:2
ADD include/certs /certs
ENV REGISTRY_HTTP_TLS_CERTIFICATE=/certs/client.cert
ENV REGISTRY_HTTP_TLS_KEY=/certs/client.key
"""


def pkg_filename(relative_path):
    return pkg_resources.resource_filename(__name__, relative_path)


def deploy_testing_registry(tunnel, test_dir, agent_list):
    """Method does the following:
    1. utilizes the localhost to generate self signed certs
    2. creates custom registry image with certs baked in
    3. deploys custom registry on test host
    4. Adds CA cert to test host and all nodes in agent list
    5. Transfers test_server resouces to test host and builds
        test_server docker image
    6. Pushes test_server image to custom registry on test host

    Args:
        tunnel: instance of SSHTunnel connecting to test host
        test_dir: directory on test host where files can land
        agent_list: list of IPs that might need to pull from
            this registry
    """
    log.info('Generating Self-Signed Certificate...')
    check_call(['openssl', 'version'])  # Check that openssl is accessible
    temp_dir = tempfile.mkdtemp()
    certs_dir = join(temp_dir, 'include', 'certs')
    check_call(['mkdir', '-p', certs_dir])

    # copy ssl-ca-conf into tmp certs dir
    orig_ca_conf = pkg_filename('openssl/openssl-ca.cnf')
    ca_conf = join(certs_dir, 'openssl-ca.cnf')
    shutil.copy(orig_ca_conf, ca_conf)
    # configure Root CA
    rootca_cert = join(certs_dir, 'cacert.pem')
    check_call(['openssl', 'req', '-x509', '-config', ca_conf,
                '-newkey', 'rsa:4096', '-sha256', '-days', '1000', '-subj',
                '/C=US/ST=California/L=San Francisco/O=Mesosphere/CN=DCOS Test CA',
                '-nodes', '-out', rootca_cert, '-outform', 'PEM'], cwd=temp_dir)
    # make server conf
    orig_server_conf = pkg_filename('openssl/openssl-server.cnf')
    server_conf = join(certs_dir, 'openssl-server.cnf')
    shutil.copy(orig_server_conf, server_conf)
    with open(server_conf, 'a') as fh:
        fh.write('DNS.1 = '+tunnel.host+'\n')
        fh.write('IP.1 = '+tunnel.host+'\n')

    # make client CSR
    client_csr = join(certs_dir, 'client.csr')
    check_call(['openssl', 'req', '-config', server_conf, '-newkey',
                'rsa:2048', '-sha256', '-subj',
                '/C=US/ST=California/L=San Francisco/O=Mesosphere/CN='+tunnel.host,
                '-nodes', '-out', client_csr, '-outform', 'PEM'], cwd=temp_dir)
    check_call(['openssl', 'req', '-text', '-noout', '-verify', '-in', client_csr], cwd=temp_dir)

    # make client cert
    check_call(['touch', join(certs_dir, 'index.txt')])
    write_string(join(certs_dir, 'serial.txt'), '01')
    client_cert = join(certs_dir, 'client.cert')
    check_call(['openssl', 'ca', '-batch', '-config', ca_conf,
                '-policy', 'signing_policy', '-extensions', 'signing_req',
                '-out', client_cert, '-infiles', client_csr], cwd=temp_dir)
    check_call(['openssl', 'x509', '-noout', '-text', '-in', client_cert], cwd=temp_dir)

    # setup the client certs in the right folders
    client_key = join(certs_dir, 'client.key')
    for name in [tunnel.host, tunnel.host+':5000']:
        hostname_dir = join(certs_dir, name)
        check_call(['mkdir', '-p', hostname_dir])
        shutil.copy(client_cert, join(hostname_dir, 'client.cert'))
        shutil.copy(client_key, join(hostname_dir, 'client.key'))
        shutil.copy(rootca_cert, join(hostname_dir, name+'.crt'))

    # build self-signed registry for shipping
    log.info('Building and exporting custom registry')
    write_string(join(temp_dir, 'Dockerfile'), REGISTRY_DOCKERFILE)
    check_call(['docker', 'build', '-t', 'registry:custom', temp_dir])
    local_tar_path = join(temp_dir, 'registry_custom.tar')
    check_call(['docker', 'save', '-o', local_tar_path, 'registry:custom'])

    log.info('Transferring and loading custom registry image')
    remote_tar_path = join(test_dir, 'registry_custom.tar')
    tunnel.write_to_remote(local_tar_path, remote_tar_path)
    tunnel.remote_cmd(['docker', 'load', '-i', remote_tar_path])
    log.info('Starting registry')
    tunnel.remote_cmd(['docker', 'run', '-d', '--restart=always', '-p',
                       '5000:5000', '--name', 'registry', 'registry:custom'])

    log.info('Tar-ing certs dir')
    certs_tarball = join(temp_dir, 'certs.tgz')
    check_call(['tar', 'czf', certs_tarball, 'certs'], cwd=join(temp_dir, 'include'))
    log.info(certs_tarball)
    cert_transfer_path = join(test_dir, 'certs.tgz')
    docker_conf_chain = (
            ['docker', 'version'],  # checks that docker is available w/o sudo
            ['tar', 'xzf', cert_transfer_path, '-C', test_dir],
            ['sudo', 'cp', '-R', join(test_dir, 'certs'), '/etc/docker/certs.d/'])
    tunnel.write_to_remote(certs_tarball, cert_transfer_path)

    log.info('Setting up SSH key on test host for daisy-chain-ing')
    remote_key_path = join(test_dir, 'test_ssh_key')
    tunnel.write_to_remote(tunnel.ssh_key_path, remote_key_path)
    tunnel.remote_cmd(['chmod', '600', remote_key_path])
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

    log.info('Creating test_server on: '+tunnel.host)
    test_server_docker = pkg_filename('docker/test_server/Dockerfile')
    test_server_script = pkg_filename('docker/test_server/test_server.py')
    test_server_dir = join(test_dir, 'test_server')
    test_server_tag = tunnel.host + ':5000/test_server'
    tunnel.remote_cmd(['mkdir', '-p', test_server_dir])
    tunnel.write_to_remote(test_server_docker, join(test_server_dir, 'Dockerfile'))
    tunnel.write_to_remote(test_server_script, join(test_server_dir, 'test_server.py'))
    log.info('Building test_server Docker image on test host')
    tunnel.remote_cmd(['docker', 'build', '-t', test_server_tag, test_server_dir])
    log.info('Pushing built test server to registry')
    tunnel.remote_cmd(['docker', 'push', test_server_tag])
    log.debug('Cleaning up test_server files')
    tunnel.remote_cmd(['rm', '-rf', test_server_dir])


def integration_test(
        tunnel, test_dir, registry,
        dcos_dns, master_list, agent_list, public_agent_list,
        test_dns_search, provider, ci_flags, timeout=None,
        aws_access_key_id='', aws_secret_access_key='', region='', add_env=None):
    """Runs integration test on host

    Args:
        tunnel: instance of SSHTunnel
        test_dir: filepath on test host where files can land
        registry: IP or hostname for registry to pull test_server from
        dcos_dns: IP or hostname for DCOS DNS
        master_list: list of IP addresses for masters
        agent_list: list of IP address for private agents
        public_agent_list: list of IP address for public agents
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
        'REGISTRY_HOST='+registry,
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
    shutil.copy(test_script, join(temp_dir, 'integration_test.py'))
    shutil.copy(pytest_docker, join(temp_dir, 'Dockerfile'))
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
        log.info('All tests passed!')
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
