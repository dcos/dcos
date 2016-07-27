#!/usr/bin/env python3
"""Integration test for advanced install method with CCM provided VPC

The following environment variables control test procedure:

CCM_VPC_HOSTS: comma separated IP addresses that are accesible from localhost (default=None)
    If provided, ssh_key must be in current working directory and hosts must
    be accessible using ssh -i ssh_key centos@IP

INSTALLER_URL: URL that curl can grab the installer from (default=None)
    This option is only used if CCM_HOST_SETUP=true. See above.

CI_FLAGS: string (default=None)
    If provided, this string will be passed directly to py.test as in:
    py.test -vv CI_FLAGS integration_test.py

TEST_ADD_CONFIG: string (default=None)
    A path to a YAML config file containing additional values that will be injected
    into the DCOS config during genconf

TEST_ADD_ENV_*: string (default=None)
    Any number of environment variables can be passed to integration_test.py if
    prefixed with 'TEST_ADD_ENV_'. The prefix will be removed before passing
"""
import logging
import os
import random
import stat
import string
import sys
from contextlib import closing
from os.path import join

import pkg_resources
from retrying import retry

import test_util.ccm
import test_util.installer_api_test
import test_util.test_runner
from ssh.ssh_tunnel import SSHTunnel, TunnelCollection

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
log = logging.getLogger(__name__)

DEFAULT_AWS_REGION = 'us-west-2'


def pkg_filename(relative_path):
    return pkg_resources.resource_filename(__name__, relative_path)


def get_local_address(tunnel, remote_dir):
    """Uses checked-in IP detect script to report local IP mapping
    Args:
        tunnel (SSHTunnel): see ssh.ssh_tunnel.SSHTunnel
        remote_dir (str): path on hosts for ip-detect to be copied and run in

    Returns:
        dict[public_IP] = local_IP
    """
    ip_detect_script = pkg_resources.resource_filename('gen', 'ip-detect/aws.sh')
    tunnel.write_to_remote(ip_detect_script, join(remote_dir, 'ip-detect.sh'))
    local_ip = tunnel.remote_cmd(['bash', join(remote_dir, 'ip-detect.sh')]).decode('utf-8').strip('\n')
    assert len(local_ip.split('.')) == 4
    return local_ip


def make_vpc():
    """uses CCM to provision a test VPC of minimal size
    """
    random_identifier = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
    unique_cluster_id = "adv-install-test-{}".format(random_identifier)
    log.info("Spinning up AWS VPC via CCM with ID: {}".format(unique_cluster_id))
    ccm = test_util.ccm.Ccm()
    vpc = ccm.create_vpc(
        name=unique_cluster_id,
        time=60,
        instance_count=5,  # 1 bootstrap, 1 master, 2 agents, 1 public agent
        instance_type='m4.xlarge',
        instance_os='cent-os-7-dcos-prereqs',
        region=DEFAULT_AWS_REGION,
        key_pair_name=unique_cluster_id)
    return vpc


def check_environment():
    """Test uses environment variables to play nicely with TeamCity config templates
    Grab all the environment variables here to avoid setting params all over

    Returns:
        object: generic object used for cleanly passing options through the test

    Raises:
        AssertionError: if any environment variables or resources are missing
            or do not conform
    """
    options = type('Options', (object,), {})()

    options.host_list = os.getenv('CCM_VPC_HOSTS')
    options.installer_url = os.environ['INSTALLER_URL']
    options.ci_flags = os.getenv('CI_FLAGS', '')
    options.add_config_path = os.getenv('TEST_ADD_CONFIG')
    if options.add_config_path:
        assert os.path.isfile(options.add_config_path)

    add_env = {}
    prefix = 'TEST_ADD_ENV_'
    for k, v in os.environ.items():
        if k.startswith(prefix):
            add_env[k.replace(prefix, '')] = v
    options.add_env = add_env
    return options


def main():
    options = check_environment()

    host_list = None
    vpc = None  # Set if the test owns the VPC

    if options.host_list is None:
        log.info('CCM_VPC_HOSTS not provided, requesting new VPC from CCM...')
        vpc = make_vpc()
        host_list = vpc.hosts()
        ssh_key, ssh_key_url = vpc.get_ssh_key()
        log.info('Download cluster SSH key: {}'.format(ssh_key_url))
        # Write out the ssh key to the local filesystem for the ssh lib to pick up.
        with open('ssh_key', 'w') as ssh_key_fh:
            ssh_key_fh.write(ssh_key)
    else:
        # It is from env and needs to be cast into list
        host_list = options.host_list.split(',')

    assert os.path.exists('ssh_key'), 'Valid SSH key for hosts must be in working dir!'
    # key must be chmod 600 for test_runner to use
    os.chmod('ssh_key', stat.S_IREAD | stat.S_IWRITE)

    # Create custom SSH Runnner to help orchestrate the test
    ssh_user = 'centos'
    ssh_key_path = 'ssh_key'
    remote_dir = '/home/centos'

    host_list_w_port = [i+':22' for i in host_list]

    @retry(stop_max_delay=120000)
    def establish_host_connectivity():
        """Continually try to recreate the SSH Tunnels to all hosts for 2 minutes
        """
        return closing(TunnelCollection(ssh_user, ssh_key_path, host_list_w_port))

    log.info('Checking that hosts are accessible')
    with establish_host_connectivity() as tunnels:
        local_ip = {}
        for tunnel in tunnels.tunnels:
            local_ip[tunnel.host] = get_local_address(tunnel, remote_dir)

    # use first node as bootstrap node, second node as master, all others as agents
    boot_host = host_list[0]
    boot_host_local = local_ip[host_list[0]]
    master_list = [local_ip[host_list[1]]]
    agent1 = local_ip[host_list[2]]
    agent2 = local_ip[host_list[3]]
    agent_list = [agent1, agent2]
    public_agent_list = [local_ip[host_list[4]]]
    log.info('Bootstrap host public/private IP: ' + boot_host + '/' + boot_host_local)

    log.info('Giving sudo privelege to su')
    with closing(SSHTunnel(ssh_user, ssh_key_path, boot_host)) as boot_tunnel:
        boot_tunnel.remote_cmd(['sudo', 'usermod', '-aG', 'docker', ssh_user])

    # Must create a new session for usermod to take effect
    with closing(SSHTunnel(ssh_user, ssh_key_path, boot_host)) as boot_tunnel:
        log.info('Setting up installer on boot host')

        installer = test_util.installer_api_test.DcosCliInstaller()
        installer.setup_remote(
                tunnel=boot_tunnel,
                installer_path=remote_dir+'/dcos_generate_config.sh',
                download_url=options.installer_url)

        log.info('Starting bootstrap ZooKeeper')
        zk_host = boot_host_local + ':2181'
        zk_cmd = [
            'docker', 'run', '-d', '-p', '2181:2181', '-p', '2888:2888',
            '-p', '3888:3888', 'jplock/zookeeper']
        boot_tunnel.remote_cmd(zk_cmd)

        log.info('Configuring install...')
        with open(pkg_resources.resource_filename('gen', 'ip-detect/aws.sh')) as ip_detect_fh:
            ip_detect_script = ip_detect_fh.read()
        with open('ssh_key', 'r') as key_fh:
            ssh_key = key_fh.read()
        hosting_url = 'http://'+boot_host_local
        installer.genconf(
                bootstrap_url=hosting_url,
                zk_host=zk_host,
                master_list=master_list,
                agent_list=agent_list,
                public_agent_list=public_agent_list,
                ip_detect_script=ip_detect_script,
                ssh_user=ssh_user,
                ssh_key=ssh_key,
                add_config_path=options.add_config_path)
        boot_tunnel.remote_cmd([
            'docker', 'run', '-d', '-v', remote_dir+'/genconf/serve:/usr/share/nginx/html',
            '-p', '80:80', '--restart=always', 'nginx'])

        dcos_install_path = remote_dir + '/dcos_install.sh'
        get_installer = ['curl', '-flsSv', '-o', dcos_install_path, hosting_url+'/dcos_install.sh']

        log.info("Starting install on masters")
        with closing(SSHTunnel(ssh_user, ssh_key_path, host_list[1])) as master:
            master.remote_cmd(get_installer)
            master.remote_cmd(['sudo', 'bash', dcos_install_path, '--no-block-dcos-setup', 'master'])

        log.info("Starting install on private agents")
        for host in host_list[2:4]:
            with closing(SSHTunnel(ssh_user, ssh_key_path, host)) as private_agent:
                private_agent.remote_cmd(get_installer)
                private_agent.remote_cmd(['sudo', 'bash', dcos_install_path, '--no-block-dcos-setup', 'slave'])

        log.info("Starting install on public agents")
        with closing(SSHTunnel(ssh_user, ssh_key_path, host_list[4])) as public_agent:
            public_agent.remote_cmd(get_installer)
            public_agent.remote_cmd(['sudo', 'bash', dcos_install_path, '--no-block-dcos-setup', 'slave_public'])

        log.info('Running post-flight checks with installer')

        # each postflight call takes 15 minutes before timing out
        @retry(stop_max_attempt_number=2)
        def postflight():
            installer.postflight()

        postflight()
        log.info('Postflight successful!')

    with closing(SSHTunnel(ssh_user, ssh_key_path, host_list[1])) as master_tunnel:
        # Runs dcos-image/integration_test.py inside the cluster
        result = test_util.test_runner.integration_test(
                tunnel=master_tunnel,
                test_dir=remote_dir,
                dcos_dns=master_list[0],
                master_list=master_list,
                agent_list=agent_list,
                public_agent_list=public_agent_list,
                provider='onprem',
                test_dns_search=True,
                ci_flags=options.ci_flags,
                add_env=options.add_env)

    if result == 0:
        log.info("Test successsful! Deleting VPC if provided in this run...")
        if vpc is not None:
            vpc.delete()
    else:
        log.info("Test failed! VPC will remain for debugging 1 hour from instantiation")
    if options.ci_flags:
        result = 0  # Wipe the return code so that tests can be muted in CI
    sys.exit(result)


if __name__ == "__main__":
    main()
