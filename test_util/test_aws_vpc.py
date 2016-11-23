#!/usr/bin/env python3
"""Integration test for SSH installer with AWS provided VPC

The following environment variables control test procedure:

VPC_HOSTS: comma-delimeted string of colon-delimited public:private IP pairs (default=None)
    Example: VPC_HOSTS=1.2.3.4:2.2.3.4,1.2.3.5:2.2.3.5,...
    If provided, ssh_key must be in current working directory and hosts must
    be accessible using ssh -i ssh_key centos@IP

HOST_SETUP: true or false (default=true)
    If true, test will attempt to download the installer from INSTALLER_URL, start the bootstap
    ZK (if required), and setup the integration_test.py requirements (setup test runner, test
    registry, and test app in registry).
    If false, test will skip the above steps

MASTERS: integer (default=1)
    The number of masters to create from VPC_HOSTS or a newly created VPC.

AGENTS: integer (default=2)
    The number of agents to create from VPC_HOSTS or a newly created VPC.

PUBLIC_AGENTS: integer (default=1)
    The number of public agents to create from VPC_HOSTS or a newly created VPC.

DCOS_SSH_KEY_PATH: string (default='default_ssh_key')
    Use to set specific ssh key path. Otherwise, script will expect key at default_ssh_key

INSTALLER_URL: URL that curl can grab the installer from (default=None)
    This option is only used if HOST_SETUP=true. See above.

USE_INSTALELR_API: true or false (default=None)
    starts installer web server as daemon when HOST_SETUP=true and proceeds to only
    communicate with the installer via the API. In this mode, exhibitor backend is set
    to static and a bootstrap ZK is not needed (see HOST_SETUP)

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
import string
import sys

import test_util.aws
import test_util.cluster

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
log = logging.getLogger(__name__)

DEFAULT_AWS_REGION = os.getenv('DEFAULT_AWS_REGION', 'eu-central-1')


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

    if 'VPC_HOSTS' in os.environ:
        options.host_list = [
            test_util.aws.Host(*host_str.split(':')) for host_str in os.environ['VPC_HOSTS'].split(',')
        ]
    else:
        options.host_list = None

    if 'HOST_SETUP' in os.environ:
        assert os.environ['HOST_SETUP'] in ['true', 'false']
    options.do_setup = os.getenv('HOST_SETUP', 'true') == 'true'

    if options.do_setup:
        assert 'INSTALLER_URL' in os.environ, 'INSTALLER_URL must be set!'
        options.installer_url = os.environ['INSTALLER_URL']
    else:
        options.installer_url = None

    options.masters = int(os.environ.get('MASTERS', '1'))
    options.agents = int(os.environ.get('AGENTS', '2'))
    options.public_agents = int(os.environ.get('PUBLIC_AGENTS', '1'))

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
    options.instance_type = os.environ.get('DCOS_AWS_INSTANCE_TYPE', 'm4.xlarge')

    options.ssh_key_path = os.environ.get('DCOS_SSH_KEY_PATH', 'default_ssh_key')

    options.add_config_path = os.getenv('TEST_ADD_CONFIG')
    if options.add_config_path:
        assert os.path.isfile(options.add_config_path)

    add_env = {}
    prefix = 'TEST_ADD_ENV_'
    for k, v in os.environ.items():
        if k.startswith(prefix):
            add_env[k.replace(prefix, '')] = v
    options.add_env = add_env

    options.pytest_cmd = os.getenv('DCOS_PYTEST_CMD', 'py.test -vv -s -rs ' + options.ci_flags)
    return options


def main():
    options = check_environment()

    cluster = None
    vpc = None
    if options.host_list is None:
        log.info('VPC_HOSTS not provided, requesting new VPC ...')
        random_identifier = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
        unique_cluster_id = "installer-test-{}".format(random_identifier)
        log.info("Spinning up AWS VPC with ID: {}".format(unique_cluster_id))
        if options.test_install_prereqs:
            os_name = "cent-os-7"
        else:
            os_name = "cent-os-7-dcos-prereqs"
        # TODO(mellenburg): Switch to using generated keys
        bw = test_util.aws.BotoWrapper(
            region=DEFAULT_AWS_REGION,
            aws_access_key_id=options.aws_access_key_id,
            aws_secret_access_key=options.aws_secret_access_key)
        vpc, ssh_info = test_util.aws.VpcCfStack.create(
            stack_name=unique_cluster_id,
            instance_type=options.instance_type,
            instance_os=os_name,
            # An instance for each cluster node plus the bootstrap.
            instance_count=(options.masters + options.agents + options.public_agents + 1),
            admin_location='0.0.0.0/0',
            key_pair_name='default',
            boto_wrapper=bw)
        vpc.wait_for_stack_creation()

        cluster = test_util.cluster.Cluster.from_vpc(
            vpc,
            ssh_info,
            ssh_key_path=options.ssh_key_path,
            num_masters=options.masters,
            num_agents=options.agents,
            num_public_agents=options.public_agents,
        )
    else:
        # Assume an existing onprem CentOS cluster.
        cluster = test_util.cluster.Cluster.from_hosts(
            ssh_info=test_util.aws.SSH_INFO['centos'],
            ssh_key_path=options.ssh_key_path,
            hosts=options.host_list,
            num_masters=options.masters,
            num_agents=options.agents,
            num_public_agents=options.public_agents,
        )

    test_util.cluster.install_dcos(
        cluster,
        installer_url=options.installer_url,
        setup=options.do_setup,
        api=options.use_api,
        add_config_path=options.add_config_path,
        # If we don't want to test the prereq install, use offline mode to avoid it.
        installer_api_offline_mode=(not options.test_install_prereqs),
        install_prereqs=options.test_install_prereqs,
        install_prereqs_only=options.test_install_prereqs_only,
    )

    if options.test_install_prereqs and options.test_install_prereqs_only:
        # install_dcos() exited after running prereqs, so we're done.
        if vpc:
            vpc.delete()
        sys.exit(0)

    result = test_util.cluster.run_integration_tests(
        cluster,
        # Setting dns_search: mesos not currently supported in API
        region=DEFAULT_AWS_REGION,
        aws_access_key_id=options.aws_access_key_id,
        aws_secret_access_key=options.aws_secret_access_key,
        add_env=options.add_env,
        pytest_cmd=options.pytest_cmd,
    )

    if result == 0:
        log.info("Test successful! Deleting VPC if provided in this run.")
        if vpc:
            vpc.delete()
    else:
        log.info("Test failed! VPC will remain for debugging 1 hour from instantiation")
    if options.ci_flags:
        result = 0  # Wipe the return code so that tests can be muted in CI
    sys.exit(result)


if __name__ == "__main__":
    main()
