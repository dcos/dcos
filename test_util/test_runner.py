#!/usr/bin/env python3
"""Module for running integration_test.py inside of a remote cluster
Parameters for integration_test.py are passed via the same environment variables
Note: ssh_user must be able to use docker without sudo priveleges
"""
import logging
import os
import shutil
import tempfile
import time
from os.path import join
from subprocess import CalledProcessError, TimeoutExpired, check_call

import pkg_resources

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
log = logging.getLogger(__name__)

TEST_DOCKERD_CONFIG = """[Service]
Restart=always
StartLimitInterval=0
RestartSec=15
ExecStart=
ExecStart=/usr/bin/docker daemon -H fd:// --storage-driver=overlay --insecure-registry={}:5000
"""

REGISTRY_DOCKERFILE = """FROM registry:2
ADD {} /certs
ENV REGISTRY_HTTP_TLS_CERTIFICATE=/certs/client.cert
ENV REGISTRY_HTTP_TLS_KEY=/certs/client.key
"""


def create_togo_registry(tunnel, registry_host, test_dir):
    temp_dir = tempfile.mkdtemp()
    certs_dir = join(temp_dir, 'certs')

    # copy ssl-ca-conf into tmp certs dir
    orig_ca_conf = pkg_filename('extra/openssl-ca.cnf')
    ca_conf = join(certs_dir, 'openssl-ca.cnf')
    shutil.copy(orig_ca_conf, ca_conf)
    # configure Root CA
    rootca_cert = join(certs_dir, 'cacert.pem')
    check_call(['openssl', 'req', 'x509', '-config', ca_conf,
                '-newkey', 'rsa:4096', '-sha256', '-subj',
                '"/C=US/ST=California/L=San Francisco/O=Mesosphere/CN=DCOS Test CA"',
                '-nodes', '-out', rootca_cert, '-outform', 'PEM'])
    # make server conf
    orig_server_conf = pkg_filename('extra/openssl-server.cnf')
    server_conf = join(certs_dir, 'openssl-server.cnf')
    shutil.copy(orig_server_conf, server_conf)
    with open(server_conf, 'a') as fh:
        fh.write('DNS.1 = '+registry_host+'\n')
        fh.write('IP.1 = '+registry_host+'\n')

    # make client CSR
    client_csr = join(certs_dir, 'client.csr')
    check_call(['openssl', 'req', '-config', 'server_conf', '-newkey',
                'rsa:2048', '-sha256', '-subj',
                '"/C=US/ST=California/L=San Francisco/O=Mesosphere/CN={}"'.format(registry_host),
                '-nodes', '-out', client_csr, '-outform', 'PEM'])
    check_call(['openssl', 'req', '-text', '-noout', '-verify', '-in', client_csr])

    # touch index.txt
    check_call(['touch', join(certs_dir, 'index.txt')])
    # make serial.txt
    check_call(['echo', '01', '>', join(certs_dir, 'serial.txt')])

    # make client cert
    client_cert = join(certs_dir, 'client.cert')
    check_call(['openssl', 'ca', '-batch', '-config', ca_conf,
                '-policy', 'signing_policy', '-extensions', 'signing_req',
                '-out', client_cert, '-infiles', client_csr])
    check_call(['openssl', 'x509', '-noout', '-text', '-in', client_cert])

    # finally, setup the client certs in the right folders
    client_key = join(certs_dir, 'client.key')
    for name in [registry_host, registry_host+':5000']:
        hostname_dir = join(certs_dir, name)
        os.mkdir(hostname_dir)
        shutil.copy(client_cert, join(hostname_dir, 'client.cert'))
        shutil.copy(client_key, join(hostname_dir, 'client.key'))
        shutil.copy(rootca_cert, join(hostname_dir, name+'.crt'))

    # build self-signed registry for shipping
    with open(join(temp_dir, 'Dockerfile'), 'w') as fh:
        fh.write(REGISTRY_DOCKERFILE.format(certs_dir))

    check_call(['docker', 'build', '-t', 'registry:custom', '.'], cwd=temp_dir)
    local_tar_path = join(temp_dir, 'registry_custom.tar')
    check_call(['docker', 'save', '-o', local_tar_path, 'registry:custom'])
    check_call(['docker', 'rmi', 'registry:custom'])

    log.info('Transferring custom registry image tarfile')
    remote_tar_path = join(test_dir, 'registry_custom.tar')
    tunnel.write_to_remote(local_tar_path, remote_tar_path)
    log.info('Loading custom registry on '+registry_host)
    tunnel.remote_cmd(['docker', 'load', '-i', remote_tar_path])

    log.info('Starting registry')
    tunnel.remote_cmd(['docker', 'run', '-d', '--restart=always', '-p'
                       '5000:5000', '--name', 'registry', 'registry:custom'])


def start_registry():
    # @docker exec -it $(MASTER_CTR)1 \
    # docker run \
    # -d --restart=always \
    # -p 5000:5000 \
    # -v /etc/docker/certs.d:/certs \
    # -e REGISTRY_HTTP_TLS_CERTIFICATE=/certs/client.cert \
    # -e REGISTRY_HTTP_TLS_KEY=/certs/client.key \
    # --name registry \
    # registry:2
    # @$(eval REGISTRY_IP := $(firstword $(MASTER_IPS)):5000)
    # @$(call copy_registry_certs,$(REGISTRY_IP))
    # @$(call copy_registry_certs,$(REGISTRY_HOST):5000)
    # @echo "Your registry is reachable from inside the DC/OS containers at:"
    # @echo -e "\t$(REGISTRY_HOST):5000"
    # @echo -e "\t$(REGISTRY_IP)"
    pass


def pkg_filename(relative_path):
    return pkg_resources.resource_filename(__name__, relative_path)


def setup_integration_test(tunnel, test_dir, registry=None, agent_list=None):
    """Transfer resources and issues commands on host to build test app,
    host it on a docker registry, and prepare the integration_test container
    Note: we perform configuration of the nodes via a single establish tunnel
        so that the test may run through a load balance (i.e. Azure tests)

    Args:
        registry (str): address of registry host that is visible to test nodes (DCOS local IP of test_host)
        test_dir (str): path to be used for setup and file transfer on host

    Returns:
        result from async chain that can be checked later for success
    """
    test_server_docker = pkg_filename('docker/test_server/Dockerfile')
    test_server_script = pkg_filename('docker/test_server/test_server.py')
    pytest_docker = pkg_filename('docker/py.test/Dockerfile')
    log.info('Setting up integration_test.py to run on ' + tunnel.host)
    tunnel.remote_cmd(['mkdir', '-p', test_dir])

    if not registry:
        log.warning('No registry provided; using test host as registry')
        log.warning('Assuming that test host is a node in DCOS')
        log.info('Finding IP local of test host')
        registry = tunnel.remote_cmd(['/opt/mesosphere/bin/detect_ip'])

    log.info('Setting up SSH key on test host for daisy-chain-ing')
    remote_key_path = join(test_dir, 'test_ssh_key')
    tunnel.write_to_remote(tunnel.ssh_key_path, remote_key_path)
    tunnel.remote_cmd(['chmod', '600', remote_key_path])

    log.info('Reconfiguring all dockerd to trust insecurity registry: ' + registry)
    with open('execstart.conf', 'w') as conf_fh:
        conf_fh.write(TEST_DOCKERD_CONFIG.format(registry))
    conf_transfer_path = join(test_dir, 'execstart.conf')
    docker_conf_chain = (
        ['docker', 'version'],  # checks that docker is available w/o sudo
        ['sudo', 'cp', conf_transfer_path, '/etc/systemd/system/docker.service.d/execstart.conf'],
        ['sudo', 'systemctl', 'daemon-reload'],
        ['sudo', 'systemctl', 'restart', 'docker'])
    log.info('Reconfiguring dockerd on test host')
    tunnel.write_to_remote('execstart.conf', conf_transfer_path)
    for cmd in docker_conf_chain:
        tunnel.remote_cmd(cmd)
    for agent in agent_list:
        log.info('Reconfiguring dockerd on ' + agent)
        target = "{}@{}".format(tunnel.ssh_user, agent)
        target_scp = "{}:{}".format(target, conf_transfer_path)
        ssh_opts = ['-oStrictHostKeyChecking=no', '-oUserKnownHostsFile=/dev/null']
        scp_cmd = ['/usr/bin/scp', '-i', remote_key_path] + ssh_opts
        remote_scp = scp_cmd + [conf_transfer_path, target_scp]
        tunnel.remote_cmd(remote_scp)
        chain_prefix = ['/usr/bin/ssh', '-tt', '-i', remote_key_path] + ssh_opts + [target]
        for cmd in docker_conf_chain:
            tunnel.remote_cmd(chain_prefix+cmd)

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
        '{}:5000/test_server'.format(registry), '.'])
    log.info('Pushing built test server to insecure registry')
    tunnel.remote_cmd(['docker', 'push', "{}:5000/test_server".format(registry)])
    log.debug('Cleaning up test_server files')
    tunnel.remote_cmd(['rm', '-rf', join(test_dir, 'test_server')])
    log.info('Building base integration_test.py container on test host')
    tunnel.remote_cmd(['mkdir', '-p', join(test_dir, 'py.test')])
    tunnel.write_to_remote(pytest_docker, join(test_dir, 'py.test/Dockerfile'))
    tunnel.remote_cmd([
        'cd', join(test_dir, 'py.test'), '&&', 'docker', 'build', '-t', 'py.test', '.'])
    tunnel.remote_cmd(['rm', '-rf', join(test_dir, 'py.test')])


def integration_test(
        tunnel, test_dir,
        dcos_dns, master_list, agent_list, registry_host,
        variant, test_dns_search, ci_flags, timeout=None,
        aws_access_key_id='', aws_secret_access_key='', region=''):
    """Runs integration test on host

    Args:
        test_dir: string representing host where integration_test.py exists on test_host
        dcos_dns: string representing IP of DCOS DNS host
        master_list: string of comma separated master addresses
        agent_list: string of comma separated agent addresses
        registry_host: string for address where marathon can pull test app
        variant: 'ee' or 'default'
        test_dns_search: if set to True, test for deployed mesos DNS app
        ci_flags: optional additional string to be passed to test
        # The following variables correspond to currently disabled tests
        aws_access_key_id: needed for REXRAY tests
        aws_secret_access_key: needed for REXRAY tests
        region: string indicating AWS region in which cluster is running
    """
    log.info('Transfering integration_test.py')
    test_script = pkg_filename('integration_test.py')
    tunnel.remote_cmd(['mkdir', '-p', test_dir])
    tunnel.write_to_remote(test_script, test_dir+'/integration_test.py')

    test_container_name = 'int_test_' + str(int(time.time()))
    dns_search = 'true' if test_dns_search else 'false'
    test_cmd = [
        'docker', 'run', '-v', test_dir+'/integration_test.py:/integration_test.py',
        '-e', 'DCOS_DNS_ADDRESS=http://'+dcos_dns,
        '-e', 'MASTER_HOSTS='+','.join(master_list),
        '-e', 'PUBLIC_MASTER_HOSTS='+','.join(master_list),
        '-e', 'SLAVE_HOSTS='+','.join(agent_list),
        '-e', 'REGISTRY_HOST='+registry_host,
        '-e', 'DCOS_VARIANT='+variant,
        '-e', 'DNS_SEARCH='+dns_search,
        '-e', 'AWS_ACCESS_KEY_ID='+aws_access_key_id,
        '-e', 'AWS_SECRET_ACCESS_KEY='+aws_secret_access_key,
        '-e', 'AWS_REGION='+region,
        '--net=host', '--name='+test_container_name, 'py.test', 'py.test',
        '-vv', ci_flags, '/integration_test.py']
    log.info('Running integration test...')
    try:
        tunnel.remote_cmd(test_cmd, timeout=timeout)
        log.info('Successful test run!')
    except TimeoutExpired as e:
        log.error('Test failed due to timing out after {} seconds'.format(timeout))
        raise e
    except CalledProcessError as e:
        log.error('Test failed!')
        raise e
    finally:
        get_logs_cmd = ['docker', 'logs', test_container_name]
        test_log = tunnel.remote_cmd(get_logs_cmd, raw_output=True)
        log_file = 'integration_test.log'
        with open(log_file, 'wb') as fh:
            fh.write(test_log)
        log.info('Logs from test container can be found in '+log_file)
