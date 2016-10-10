#!/usr/bin/env python3
"""Deploys DC/OS AWS CF template and then runs integration_test.py

The following environment variables control test procedure:

AGENTS: integer (default=2)
    The number of agents to create in a new cluster.

PUBLIC_AGENTS: integer (default=1)
    The number of public agents to create in a new cluster.

DCOS_TEMPLATE_URL: string
    The template to be used for deployment testing

DCOS_STACK_NAME: string
    Instead of providing a template, supply the name (or id) of an already
    existing cluster

DCOS_SSH_KEY_PATH: string
    path for the SSH key to be used with a preexiting cluster.
    Defaults to 'default_ssh_key'

DCOS_ADVANCED_TEMPLATE: boolean (default:false)
    If true, then DCOS_STACK_NAME is for a DC/OS advanced stack

DCOS_HOST_OS: 'coreos' or 'centos'
    This must be set only if you are attaching to an already provisioned
    DC/OS Advanced template cluster

TEST_DCOS_RESILIENCY: true/false (default: false)
    Will setup a cluster for resiliency testing and then run the resiliency tests
    after the standard integration tests

CI_FLAGS: string (default=None)
    If provided, this string will be passed directly to py.test as in:
    py.test -vv CI_FLAGS integration_test.py

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
from gen.calc import calculate_environment_variable
from test_util.helpers import gather_prefix_env

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
log = logging.getLogger(__name__)


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

    # Defaults
    options.ci_flags = os.getenv('CI_FLAGS', '')
    options.aws_region = os.getenv('DEFAULT_AWS_REGION', 'eu-central-1')
    options.gateway = os.getenv('DCOS_ADVANCED_GATEWAY', None)
    options.vpc = os.getenv('DCOS_ADVANCED_VPC', None)
    options.private_subnet = os.getenv('DCOS_ADVANCED_PRIVATE_SUBNET', None)
    options.public_subnet = os.getenv('DCOS_ADVANCED_PUBLIC_SUBNET', None)
    options.host_os = os.getenv('DCOS_HOST_OS', 'coreos')
    options.agents = int(os.environ.get('AGENTS', '2'))
    options.public_agents = int(os.environ.get('PUBLIC_AGENTS', '1'))
    options.ssh_key_path = os.getenv('DCOS_SSH_KEY_PATH', 'default_ssh_key')
    options.test_resiliency = os.getenv('TEST_DCOS_RESILIENCY', 'false') == 'true'

    # Mandatory
    options.stack_name = os.getenv('DCOS_STACK_NAME', None)
    options.template_url = os.getenv('DCOS_TEMPLATE_URL', None)
    if not options.template_url:
        assert options.stack_name is not None, 'if DCOS_TEMPLATE_URL is not provided, '\
            'then DCOS_STACK_NAME must be specified'
        advanced = os.getenv('DCOS_ADVANCED_TEMPLATE', None)
        assert advanced is not None, 'if using DCOS_STACK_NAME, '\
            'then DCOS_ADVANCED_TEMPLATE=[true/false] must be specified'
        options.advanced = advanced == 'true'
    else:
        options.advanced = not options.template_url.endswith('single-master.cloudformation.json') and \
            not options.template_url.endswith('multi-master.cloudformation.json')
    # Required
    options.aws_access_key_id = calculate_environment_variable('AWS_ACCESS_KEY_ID')
    options.aws_secret_access_key = calculate_environment_variable('AWS_SECRET_ACCESS_KEY')

    options.add_env = gather_prefix_env('TEST_ADD_ENV_')
    options.pytest_dir = os.getenv('DCOS_PYTEST_DIR', '/opt/mesosphere/active/dcos-integration-test')
    options.pytest_cmd = os.getenv('DCOS_PYTEST_CMD', 'py.test -vv -rs ' + options.ci_flags)
    if options.test_resiliency:
        options.pytest_cmd += ' --resiliency '
    return options


def main():
    options = check_environment()
    cf, ssh_info = provide_cluster(options)
    cluster = test_util.cluster.Cluster.from_cloudformation(cf, ssh_info, options.ssh_key_path)

    result = test_util.cluster.run_integration_tests(
        cluster,
        region=options.aws_region,
        aws_access_key_id=options.aws_access_key_id,
        aws_secret_access_key=options.aws_secret_access_key,
        test_dns_search=False,
        add_env=options.add_env,
        pytest_dir=options.pytest_dir,
        pytest_cmd=options.pytest_cmd,
    )
    if result == 0:
        log.info('Test successsful! Deleting CloudFormation...')
        cf.delete()
    else:
        logging.warning('Test exited with an error')
    if options.ci_flags:
        result = 0  # Wipe the return code so that tests can be muted in CI
    sys.exit(result)


def provide_cluster(options):
    bw = test_util.aws.BotoWrapper(
        region=options.aws_region,
        aws_access_key_id=options.aws_access_key_id,
        aws_secret_access_key=options.aws_secret_access_key)
    if not options.stack_name:
        random_id = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
        stack_name = 'CF-integration-test-{}'.format(random_id)
        log.info('Spinning up AWS CloudFormation with ID: {}'.format(stack_name))
        # TODO(mellenburg): use randomly generated keys this key is delivered by CI or user
        if options.advanced:
            cf, ssh_info = test_util.aws.DcosCfAdvanced.create(
                stack_name=stack_name,
                boto_wrapper=bw,
                template_url=options.template_url,
                private_agents=options.agents,
                public_agents=options.public_agents,
                key_pair_name='default',
                private_agent_type='m3.xlarge',
                public_agent_type='m3.xlarge',
                master_type='m3.xlarge',
                vpc=options.vpc,
                gateway=options.gateway,
                private_subnet=options.private_subnet,
                public_subnet=options.public_subnet)
        else:
            cf, ssh_info = test_util.aws.DcosCfSimple.create(
                stack_name=stack_name,
                template_url=options.template_url,
                private_agents=options.agents,
                public_agents=options.public_agents,
                admin_location='0.0.0.0/0',
                key_pair_name='default',
                boto_wrapper=bw)
        cf.wait_for_stack_creation()
    else:
        if options.advanced:
            cf = test_util.aws.DcosCfAdvanced.create(options.stack_name, bw)
        else:
            cf = test_util.aws.DcosCfSimple(options.stack_name, bw)
        ssh_info = test_util.aws.SSH_INFO[options.host_os]
        stack_name = options.stack_name
    if options.test_resiliency:
        options.add_env['AWS_STACK_NAME'] = stack_name
    return cf, ssh_info

if __name__ == '__main__':
    main()
