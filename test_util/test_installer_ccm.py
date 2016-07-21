#!/usr/bin/env python3
"""Integration test for SSH installer with CCM provided VPC

The following environment variables control test procedure:

CCM_VPC_HOSTS: comma separated IP addresses that are accesible from localhost (default=None)
    If provided, ssh_key must be in current working directory and hosts must
    be accessible using ssh -i ssh_key centos@IP

CCM_HOST_SETUP: true or false (default=true)
    If true, test will attempt to download the installer from INSTALLER_URL, start the bootstap
    ZK (if required), and setup the integration_test.py requirements (setup test runner, test
    registry, and test app in registry).
    If false, test will skip the above steps

INSTALLER_URL: URL that curl can grab the installer from (default=None)
    This option is only used if CCM_HOST_SETUP=true. See above.

USE_INSTALELR_API: true or false (default=None)
    starts installer web server as daemon when CCM_HOST_SETUP=true and proceeds to only
    communicate with the installer via the API. In this mode, exhibitor backend is set
    to static and a bootstrap ZK is not needed (see CCM_HOST_SETUP)

TEST_INSTALL_PREREQS: true or false (default=None)
    If true, the capability of the installer to setup prereqs will be tested by starting
    with bare AMIs. If false, installer 'offline mode' will be used or prereq install will
    be skipped and precooked AMIs will be used (thereby saving 5-10 minutes)

TEST_INSTALL_PREREQS_ONLY: true or false (default=false)
    If true, test will exit after preflight test passes on bare AMI. If false the test will
    continue through completion (running integration_test.py). TEST_INSTALL_PREREQS must be
    set in order to use this option

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

import passlib.hash
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

REXRAY_CONFIG = """
rexray:
  loglevel: info
  storageDrivers:
    - ec2
  volume:
    unmount:
      ignoreusedcount: true
"""


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


def make_vpc(use_bare_os=False):
    """uses CCM to provision a test VPC of minimal size (3).
    Args:
        use_bare_os: if True, vanilla AMI is used. If False, custom AMI is used
            with much faster prereq satisfaction time
    """
    random_identifier = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
    unique_cluster_id = "installer-test-{}".format(random_identifier)
    log.info("Spinning up AWS VPC via CCM with ID: {}".format(unique_cluster_id))
    if use_bare_os:
        os_name = "cent-os-7"
    else:
        os_name = "cent-os-7-dcos-prereqs"
    ccm = test_util.ccm.Ccm()
    vpc = ccm.create_vpc(
        name=unique_cluster_id,
        time=60,
        instance_count=5,  # 1 bootstrap, 1 master, 2 agents, 1 public agent
        instance_type="m4.xlarge",
        instance_os=os_name,
        region=DEFAULT_AWS_REGION,
        key_pair_name=unique_cluster_id
        )

    ssh_key, ssh_key_url = vpc.get_ssh_key()
    log.info("Download cluster SSH key: {}".format(ssh_key_url))
    # Write out the ssh key to the local filesystem for the ssh lib to pick up.
    with open("ssh_key", "w") as ssh_key_fh:
        ssh_key_fh.write(ssh_key)

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

    if 'CCM_VPC_HOSTS' in os.environ:
        options.host_list = os.environ['CCM_VPC_HOSTS'].split(',')
    else:
        options.host_list = None

    if 'CCM_HOST_SETUP' in os.environ:
        assert os.environ['CCM_HOST_SETUP'] in ['true', 'false']
    options.do_setup = os.getenv('CCM_HOST_SETUP', 'true') == 'true'

    if options.do_setup:
        assert 'INSTALLER_URL' in os.environ, 'INSTALLER_URL must be set!'
        options.installer_url = os.environ['INSTALLER_URL']
    else:
        options.installer_url = None

    assert 'USE_INSTALLER_API' in os.environ, 'USE_INSTALLER_API must be set in environ'
    assert os.environ['USE_INSTALLER_API'] in ['true', 'false']
    options.use_api = os.getenv('USE_INSTALLER_API', 'false') == 'true'

    assert 'TEST_INSTALL_PREREQS' in os.environ, 'TEST_INSTALL_PREREQS'
    assert os.environ['TEST_INSTALL_PREREQS'] in ['true', 'false']
    options.test_install_prereqs = os.getenv('TEST_INSTALL_PREREQS', 'false') == 'true'

    if 'TEST_INSTALL_PREREQS_ONLY' in os.environ:
        assert os.environ['TEST_INSTALL_PREREQS_ONLY'] in ['true', 'false']
    options.test_install_prereqs_only = os.getenv('TEST_INSTALL_PREREQS_ONLY', 'false') == 'true'

    if options.test_install_prereqs_only:
        assert os.environ['TEST_INSTALL_PREREQS'] == 'true', "Must be testing install-prereqs!"

    options.ci_flags = os.getenv('CI_FLAGS', '')
    options.aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID', '')
    options.aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY', '')

    options.add_config_path = os.getenv('TEST_ADD_CONFIG')
    if options.add_config_path:
        assert os.path.isfile(options.add_config_path)

    add_env = {}
    prefix = 'TEST_ADD_ENV_'
    for k, v in os.environ.items():
        if k.startswith(prefix):
            add_env[k.replace(prefix, '')] = v
    options.add_env = add_env

    options.pytest_dir = os.getenv('DCOS_PYTEST_DIR', '/opt/mesosphere/active/dcos-integration-test')
    options.pytest_cmd = os.getenv('DCOS_PYTEST_CMD', 'py.test -vv '+options.ci_flags)
    return options


def main():
    options = check_environment()

    host_list = None
    vpc = None  # Set if the test owns the VPC

    if options.host_list is None:
        log.info('CCM_VPC_HOSTS not provided, requesting new VPC from CCM...')
        vpc = make_vpc(use_bare_os=options.test_install_prereqs)
        host_list = vpc.hosts()
    else:
        host_list = options.host_list

    assert os.path.exists('ssh_key'), 'Valid SSH key for hosts must be in working dir!'
    # key must be chmod 600 for test_runner to use
    os.chmod('ssh_key', stat.S_IREAD | stat.S_IWRITE)

    # Create custom SSH Runnner to help orchestrate the test
    ssh_user = 'centos'
    ssh_key_path = 'ssh_key'
    remote_dir = '/home/centos'

    if options.use_api:
        installer = test_util.installer_api_test.DcosApiInstaller()
        if not options.test_install_prereqs:
            # If we dont want to test the prereq install, use offline mode to avoid it
            installer.offline_mode = True
    else:
        installer = test_util.installer_api_test.DcosCliInstaller()

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
            if options.do_setup:
                # Make the default user priveleged to use docker
                tunnel.remote_cmd(['sudo', 'usermod', '-aG', 'docker', ssh_user])

    # use first node as bootstrap node, second node as master, all others as agents
    test_host = host_list[0]
    test_host_local = local_ip[host_list[0]]
    master_list = [local_ip[host_list[1]]]
    agent1 = local_ip[host_list[2]]
    agent2 = local_ip[host_list[3]]
    agent_list = [agent1, agent2]
    public_agent_list = [local_ip[host_list[4]]]
    log.info('Test host public/private IP: ' + test_host + '/' + test_host_local)

    with closing(SSHTunnel(ssh_user, ssh_key_path, test_host)) as test_host_tunnel:
        log.info('Setting up installer on test host')

        installer.setup_remote(
                tunnel=test_host_tunnel,
                installer_path=remote_dir+'/dcos_generate_config.sh',
                download_url=options.installer_url)
        if options.do_setup:
            # only do on setup so you can rerun this test against a living installer
            log.info('Verifying installer password hashing')
            test_pass = 'testpassword'
            hash_passwd = installer.get_hashed_password(test_pass)
            assert passlib.hash.sha512_crypt.verify(test_pass, hash_passwd), 'Hash does not match password'
            if options.use_api:
                installer.start_web_server()

        with open(pkg_resources.resource_filename("gen", "ip-detect/aws.sh")) as ip_detect_fh:
            ip_detect_script = ip_detect_fh.read()
        with open('ssh_key', 'r') as key_fh:
            ssh_key = key_fh.read()
        # Using static exhibitor is the only option in the GUI installer
        if options.use_api:
            log.info('Installer API is selected, so configure for static backend')
            zk_host = None  # causes genconf to use static exhibitor backend
        else:
            log.info('Installer CLI is selected, so configure for ZK backend')
            zk_host = test_host_local + ':2181'
            zk_cmd = [
                    'sudo', 'docker', 'run', '-d', '-p', '2181:2181', '-p',
                    '2888:2888', '-p', '3888:3888', 'jplock/zookeeper']
            test_host_tunnel.remote_cmd(zk_cmd)

        log.info("Configuring install...")
        installer.genconf(
                zk_host=zk_host,
                master_list=master_list,
                agent_list=agent_list,
                public_agent_list=public_agent_list,
                ip_detect_script=ip_detect_script,
                ssh_user=ssh_user,
                ssh_key=ssh_key,
                add_config_path=options.add_config_path,
                rexray_config=REXRAY_CONFIG)

        log.info("Running Preflight...")
        if options.test_install_prereqs:
            # Runs preflight in --web or --install-prereqs for CLI
            # This may take up 15 minutes...
            installer.install_prereqs()
            if options.test_install_prereqs_only:
                if vpc:
                    vpc.delete()
                sys.exit(0)
        else:
            # Will not fix errors detected in preflight
            installer.preflight()

        log.info("Running Deploy...")
        installer.deploy()

        log.info("Running Postflight")
        installer.postflight()

    with closing(SSHTunnel(ssh_user, ssh_key_path, host_list[1])) as master_tunnel:
        # Runs dcos-image/integration_test.py inside the cluster
        result = test_util.test_runner.integration_test(
                tunnel=master_tunnel,
                test_dir=remote_dir,
                region=vpc.get_region() if vpc else DEFAULT_AWS_REGION,
                dcos_dns=master_list[0],
                master_list=master_list,
                agent_list=agent_list,
                public_agent_list=public_agent_list,
                provider='onprem',
                # Setting dns_search: mesos not currently supported in API
                test_dns_search=not options.use_api,
                aws_access_key_id=options.aws_access_key_id,
                aws_secret_access_key=options.aws_secret_access_key,
                add_env=options.add_env,
                pytest_dir=options.pytest_dir,
                pytest_cmd=options.pytest_cmd)

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
