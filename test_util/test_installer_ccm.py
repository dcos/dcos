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

MINUTEMAN_ENABLED: true or false (default=false)
    Minuteman requires a setting that is applied when CCM_HOST_SETUP=true

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
"""
import asyncio
import copy
import logging
import multiprocessing
import os
import random
import stat
import string
import sys

import passlib.hash
import pkg_resources
from retrying import retry

import test_util.ccm
import test_util.installer_api_test
from ssh.ssh_runner import MultiRunner
from ssh.utils import CommandChain, SyncCmdDelegate

AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')

DEFAULT_AWS_REGION = 'us-west-2'


def pkg_filename(relative_path):
    return pkg_resources.resource_filename(__name__, relative_path)


def run_loop(ssh_runner, chain):
    # TODO: replace with SSH Library Synchronous API

    def function():
        result = yield from ssh_runner.run_commands_chain_async([chain], block=True)
        return result

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(function())
    finally:
        loop.close()
    return result


def check_results(results, force_print=False):
    """Loops through iterable results. Only one result dict is produced per
    command, so when iterating, pop the only dict rather than iterate over it

    Args:
        results: output of loop.run_until_complete(runner.run_commands_chain_async([cmd_chain]))
        force_print: print output from loop even if it was successful

    Raises:
        AssertionError: if any of the commands have non-zero return code
    """
    for host_result in results:
        for command_result in host_result:
            assert len(command_result.keys()) == 1, 'SSH Library returned unexpected result format'
            host, data = command_result.popitem()
            err_msg = "Host {} returned exit code {} after running {}\nSTDOUT: {}\nSTDERR: {}"
            assert data['returncode'] == 0, err_msg.format(
                    host, data['returncode'], data['cmd'], '\n'.join(data['stdout']), '\n'.join(data['stderr']))
            if force_print:
                print(err_msg.format(
                    host, data['returncode'], data['cmd'], '\n'.join(data['stdout']), '\n'.join(data['stderr'])))


@retry(wait_fixed=1000, stop_max_delay=1000*300)
def get_local_addresses(ssh_runner, remote_dir):
    """Uses checked-in IP detect script to report local IP mapping
    Also functions as a test to verify cluster is up and accessible

    Args:
        ssh_runner: instance of ssh.ssh_runner.MultiRunner
        remote_dir (str): path on hosts for ip-detect to be copied and run in

    Returns:
        dict[public_IP] = local_IP
    """

    def remote(path):
        return remote_dir + '/' + path

    ip_detect_script = pkg_resources.resource_filename('gen', 'ip-detect/aws.sh')
    ip_map_chain = CommandChain('ip_map')
    ip_map_chain.add_copy(ip_detect_script, remote('ip-detect.sh'))
    ip_map_chain.add_execute(['bash', remote('ip-detect.sh')])
    mapping = {}
    result = run_loop(ssh_runner, ip_map_chain)

    # Check the running was successful
    check_results(copy.deepcopy(result))

    # Gather the local IP addresses
    for host_result in result:
        host, data = host_result[-1].popitem()  # Grab the last command trigging the script
        local_ip = data['stdout'][0].rstrip()
        assert local_ip != '', "Didn't get a valid IP for host {}:\n{}".format(host, data)
        mapping[host.split(":")[0]] = local_ip
    return mapping


def break_prereqs(ssh_runner):
    """Performs commands that will cause preflight to fail on a prepared node

    Args:
        ssh_runner: instance of ssh.ssh_runner.MultiRunner
    """
    break_prereq_chain = CommandChain('break_prereqs')
    break_prereq_chain.add_execute(['sudo', 'groupdel', 'nogroup'])

    check_results(run_loop(ssh_runner, break_prereq_chain))


def test_setup(ssh_runner, registry, remote_dir, use_zk_backend):
    """Transfer resources and issues commands on host to build test app,
    host it on a docker registry, and prepare the integration_test container

    Args:
        ssh_runner: instance of ssh.ssh_runner.MultiRunner
        registry (str): address of registry host that is visible to test nodes
        remote_dir (str): path to be used for setup and file transfer on host

    Returns:
        result from async chain that can be checked later for success
    """
    test_server_docker = pkg_filename('docker/test_server/Dockerfile')
    test_server_script = pkg_filename('docker/test_server/test_server.py')
    pytest_docker = pkg_filename('docker/py.test/Dockerfile')
    test_script = pkg_filename('integration_test.py')
    test_setup_chain = CommandChain('test_setup')
    if use_zk_backend:
        test_setup_chain.add_execute([
            'sudo', 'docker', 'run', '-d', '-p', '2181:2181', '-p', '2888:2888',
            '-p', '3888:3888', 'jplock/zookeeper'])

    def remote(path):
        return remote_dir + '/' + path

    # Create test application
    test_setup_chain.add_execute(['mkdir', '-p', remote('test_server')])
    test_setup_chain.add_copy(test_server_docker, remote('test_server/Dockerfile'))
    test_setup_chain.add_copy(test_server_script, remote('test_server/test_server.py'))
    test_setup_chain.add_execute([
        'docker', 'run', '-d', '-p', '5000:5000', '--restart=always', '--name',
        'registry', 'registry:2'])
    test_setup_chain.add_execute([
        'cd', remote('test_server'), '&&', 'docker', 'build', '-t',
        '{}:5000/test_server'.format(registry), '.'])
    test_setup_chain.add_execute(['docker', 'push', "{}:5000/test_server".format(registry)])
    test_setup_chain.add_execute(['rm', '-rf', remote('test_server')])
    # Create pytest/integration test instance on remote
    test_setup_chain.add_execute(['mkdir', '-p', remote('py.test')])
    test_setup_chain.add_copy(pytest_docker, remote('py.test/Dockerfile'))
    test_setup_chain.add_copy(test_script, remote('integration_test.py'))
    test_setup_chain.add_execute([
        'cd', remote('py.test'), '&&', 'docker', 'build', '-t', 'py.test', '.'])
    test_setup_chain.add_execute(['rm', '-rf', remote('py.test')])

    check_results(run_loop(ssh_runner, test_setup_chain))


def integration_test(
        ssh_runner, dcos_dns, master_list, agent_list, region, registry_host,
        test_minuteman, test_dns_search, ci_flags):
    """Runs integration test on host
    Note: check_results() will raise AssertionError if test fails

    Args:
        ssh_runner: instance of ssh.ssh_runner.MultiRunner
        dcos_dns: string representing IP of DC/OS DNS host
        master_list: string of comma separated master addresses
        region: string indicating AWS region in which cluster is running
        agent_list: string of comma separated agent addresses
        registry_host: string for address where marathon can pull test app
        test_minuteman: if set to True then test for minuteman service
        test_dns_search: if set to True, test for deployed mesos DNS app
        ci_flags: optional additional string to be passed to test

    """
    marker_args = '-m "not minuteman"'
    if test_minuteman:
        marker_args = ''

    run_test_chain = CommandChain('run_test')
    dns_search = 'true' if test_dns_search else 'false'
    test_cmd = [
        'docker', 'run', '-v', '/home/centos/integration_test.py:/integration_test.py',
        '-e', 'DCOS_DNS_ADDRESS=http://'+dcos_dns,
        '-e', 'MASTER_HOSTS='+','.join(master_list),
        '-e', 'PUBLIC_MASTER_HOSTS='+','.join(master_list),
        '-e', 'SLAVE_HOSTS='+','.join(agent_list),
        '-e', 'REGISTRY_HOST='+registry_host,
        '-e', 'DCOS_VARIANT=default',
        '-e', 'DNS_SEARCH='+dns_search,
        '-e', 'AWS_ACCESS_KEY_ID='+AWS_ACCESS_KEY_ID,
        '-e', 'AWS_SECRET_ACCESS_KEY='+AWS_SECRET_ACCESS_KEY,
        '-e', 'AWS_REGION='+region,
        '--net=host', 'py.test', 'py.test',
        '-vv', ci_flags, marker_args, '/integration_test.py']
    print("To run this test again, ssh to test node and run:\n{}".format(' '.join(test_cmd)))
    run_test_chain.add_execute(test_cmd)

    check_results(run_loop(ssh_runner, run_test_chain), force_print=True)


def prep_hosts(ssh_runner, registry, minuteman_enabled=False):
    """Runs steps so that nodes can pass preflight checks. Nodes are expected
    to either use the custom AMI or have install-prereqs run on them. Additionally,
    Note: break_prereqs is run before this always

    Args:
        ssh_runner: instance of ssh.ssh_runner.MultiRunner
        registry: string to configure hosts with trusted registry for app deployment
        minuteman_enabled: if True, minuteman will be available after DC/OS install
    """
    host_prep_chain = CommandChain('host_prep')
    host_prep_chain.add_execute([
        'sudo', 'sed', '-i',
        "'/ExecStart=\/usr\/bin\/docker/ !b; s/$/ --insecure-registry={}:5000/'".format(registry),
        '/etc/systemd/system/docker.service.d/execstart.conf'])
    host_prep_chain.add_execute(['sudo', 'systemctl', 'daemon-reload'])
    host_prep_chain.add_execute(['sudo', 'systemctl', 'restart', 'docker'])
    host_prep_chain.add_execute(['sudo', 'groupadd', '-g', '65500', 'nogroup'])
    host_prep_chain.add_execute(['sudo', 'usermod', '-aG', 'docker', 'centos'])

    if minuteman_enabled:
        host_prep_chain.add_execute(['sudo', 'mkdir', '-p', '/etc/mesosphere/roles'])
        host_prep_chain.add_execute(['sudo', 'touch', '/etc/mesosphere/roles/minuteman'])

    check_results(run_loop(ssh_runner, host_prep_chain))


def make_vpc(use_bare_os=False):
    """uses CCM to provision a test VPC of minimal size (3).

    Args:
        use_bare_os: if True, vanilla AMI is used. If False, custom AMI is used
            with much faster prereq satisfaction time
    """
    random_identifier = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
    unique_cluster_id = "installer-test-{}".format(random_identifier)
    print("Spinning up AWS VPC via CCM with ID: {}".format(unique_cluster_id))
    if use_bare_os:
        os_name = "cent-os-7"
    else:
        os_name = "cent-os-7-dcos-prereqs"
    ccm = test_util.ccm.Ccm()
    vpc = ccm.create_vpc(
        name=unique_cluster_id,
        time=60,
        instance_count=4,  # 1 bootstrap, 1 master, 2 agents
        instance_type="m4.xlarge",
        instance_os=os_name,
        region=DEFAULT_AWS_REGION,
        key_pair_name=unique_cluster_id
        )

    ssh_key, ssh_key_url = vpc.get_ssh_key()
    print("Download cluster SSH key: {}".format(ssh_key_url))
    # Write out the ssh key to the local filesystem for the ssh lib to pick up.
    with open("ssh_key", "w") as ssh_key_fh:
        ssh_key_fh.write(ssh_key)

    return vpc


def check_environment():
    """Test uses environment variables to play nicely with TeamCity config templates

    Returns:
        object: generic object used for cleanly passing options through the test

    Raises:
        AssertionError: if any environment variables or resources are missing
            or do not conform
    """
    options = type('Options', (object,), {})()

    options.variant = os.getenv('DCOS_VARIANT', 'default')

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

    if 'MINUTEMAN_ENABLED' in os.environ:
        assert os.environ['MINUTEMAN_ENABLED'] in ['true', 'false']
    options.minuteman_enabled = os.getenv('MINUTEMAN_ENABLED', 'false') == 'true'

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
    return options


def main():
    logging.basicConfig(level=logging.DEBUG)
    options = check_environment()

    host_list = None
    vpc = None  # Set if the test owns the VPC

    if options.host_list is None:
        vpc = make_vpc(use_bare_os=options.test_install_prereqs)
        host_list = vpc.hosts()
    else:
        host_list = options.host_list

    assert os.path.exists('ssh_key'), 'Valid SSH key for hosts must be in working dir!'
    # key must be chmod 600 for SSH lib to use
    os.chmod('ssh_key', stat.S_IREAD | stat.S_IWRITE)

    # Create custom SSH Runnner to help orchestrate the test
    ssh_user = 'centos'
    ssh_key_path = 'ssh_key'
    remote_dir = '/home/centos'

    def make_runner(host_list):
        """process_timeout must be large enough for integration_test.py to run
        """
        return MultiRunner(
                host_list, ssh_user=ssh_user, ssh_key_path=ssh_key_path,
                process_timeout=1200, async_delegate=SyncCmdDelegate())

    all_host_runner = make_runner(host_list)
    test_host_runner = make_runner([host_list[0]])
    dcos_host_runner = make_runner(host_list[1:])

    print('Checking that hosts are accessible')
    local_ip = get_local_addresses(all_host_runner, remote_dir)

    print("VPC hosts: {}".format(host_list))
    # use first node as bootstrap node, second node as master, all others as agents
    registry_host = local_ip[host_list[0]]
    master_list = [local_ip[_] for _ in host_list[1:2]]
    agent_list = [local_ip[_] for _ in host_list[2:]]

    if options.use_api:
        installer = test_util.installer_api_test.DcosApiInstaller()
        if not options.test_install_prereqs:
            # If we dont want to test the prereq install, use offline mode to avoid it
            installer.offline_mode = True
    else:
        installer = test_util.installer_api_test.DcosCliInstaller()

    # If installer_url is not set, then no downloading occurs
    installer.setup_remote(
            tunnel=None,
            installer_path=remote_dir+'/dcos_generate_config.sh',
            download_url=options.installer_url,
            host=host_list[0],
            ssh_user=ssh_user,
            ssh_key_path=ssh_key_path)

    if options.do_setup:
        host_prep_chain = CommandChain('host_prep')
        host_prep_chain.add_execute([
            'sudo', 'sed', '-i',
            "'/ExecStart=\/usr\/bin\/docker/ !b; s/$/ --insecure-registry={}:5000/'".format(registry_host),
            '/etc/systemd/system/docker.service.d/execstart.conf'])
        host_prep_chain.add_execute(['sudo', 'systemctl', 'daemon-reload'])
        host_prep_chain.add_execute(['sudo', 'systemctl', 'restart', 'docker'])
        host_prep_chain.add_execute(['sudo', 'usermod', '-aG', 'docker', 'centos'])
        check_results(run_loop(test_host_runner, host_prep_chain))

    # Retrieve and test the password hash before starting web server
    test_pass = 'testpassword'
    hash_passwd = installer.get_hashed_password(test_pass)
    assert passlib.hash.sha512_crypt.verify(test_pass, hash_passwd), 'Hash does not match password'

    if options.do_setup and options.use_api:
        installer.start_web_server()

    print("Configuring install...")
    with open(pkg_resources.resource_filename("gen", "ip-detect/aws.sh")) as ip_detect_fh:
        ip_detect_script = ip_detect_fh.read()
    with open('ssh_key', 'r') as key_fh:
        ssh_key = key_fh.read()
    # Using static exhibitor is the only option in the GUI installer
    if options.use_api:
        zk_host = None  # causes genconf to use static exhibitor backend
    else:
        zk_host = registry_host + ':2181'
    # use first node as independent test/bootstrap node, second node as master, all others as slaves
    installer.genconf(
            zk_host=zk_host,
            master_list=master_list,
            agent_list=agent_list,
            ip_detect_script=ip_detect_script,
            ssh_user=ssh_user,
            ssh_key=ssh_key)

    # Test install-prereqs. This may take up 15 minutes...
    if options.test_install_prereqs:
        installer.install_prereqs()
        if options.test_install_prereqs_only:
            if vpc:
                vpc.delete()
            sys.exit(0)

    test_setup_handler = None
    if options.do_setup:
        print("Making sure prereqs are broken...")
        break_prereqs(all_host_runner)
        print('Check that --preflight gives an error')
        installer.preflight(expect_errors=True)
        print("Prepping all hosts...")
        prep_hosts(dcos_host_runner, registry=registry_host, minuteman_enabled=options.minuteman_enabled)
        # This will setup the integration test and its resources
        print('Setting up test node while deploy runs...')
        # TODO: remove calls to both multiprocessing and asyncio
        # at time of writing block=False only supported for JSON delegates
        test_setup_handler = multiprocessing.Process(
                target=test_setup, args=(test_host_runner, registry_host, remote_dir, not options.use_api))
        # Wait for this to finish later as it is not required for deploy and preflight
        test_setup_handler.start()

    if not options.test_install_prereqs:
        # If we ran the prereq install test, then we already used preflight
        # Avoid running preflight twice in this case
        print("Running Preflight...")
        installer.preflight()

    print("Running Deploy...")
    installer.deploy()

    # If we needed setup, wait for it to finish
    if test_setup_handler:
        test_setup_handler.join()

    print("Running Postflight")
    installer.postflight()

    # Runs dcos-image/integration_test.py inside the cluster
    print("Test host: {}@{}:22".format(ssh_user, host_list[0]))
    integration_test(
        test_host_runner,
        region=vpc.get_region() if vpc else DEFAULT_AWS_REGION,
        dcos_dns=master_list[0],
        master_list=master_list,
        agent_list=agent_list,
        registry_host=registry_host,
        # Setting dns_search: mesos not currently supported in API
        test_dns_search=not options.use_api,
        test_minuteman=options.minuteman_enabled,
        ci_flags=options.ci_flags)

    # TODO(cmaloney): add a `--healthcheck` option which runs dcos-diagnostics
    # on every host to see if they are working.

    print("Test successsful!")
    # Delete the cluster if all was successful to minimize potential costs.
    # Failed clusters the hosts will continue running
    if vpc is not None:
        vpc.delete()


if __name__ == "__main__":
    main()
