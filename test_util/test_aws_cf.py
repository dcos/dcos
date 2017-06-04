#!/usr/bin/env python3
"""Deploys DC/OS AWS CF template and then runs integration_test.py

The following environment variables control test procedure:

AGENTS: integer (default=2)
    The number of agents to create in a new cluster.

PUBLIC_AGENTS: integer (default=1)
    The number of public agents to create in a new cluster.

DCOS_TEMPLATE_URL: string
    The template to be used for deployment testing

DCOS_HOST_OS: 'coreos' or 'centos'
    This must be set only if you are attaching to an already provisioned
    DC/OS Advanced template cluster

CI_FLAGS: string (default=None)
    If provided, this string will be passed directly to py.test as in:
    py.test -vv CI_FLAGS integration_test.py

TEST_ADD_ENV_*: string (default=None)
    Any number of environment variables can be passed to integration_test.py if
    prefixed with 'TEST_ADD_ENV_'. The prefix will be removed before passing
"""
import logging
import os
import sys
import time

import test_util.aws
import test_util.cluster
from gen.calc import calculate_environment_variable
from pkgpanda.util import write_string
from test_util.helpers import random_id

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

    # Mandatory
    options.template_url = os.getenv('DCOS_TEMPLATE_URL', None)
    options.advanced = not options.template_url.endswith('single-master.cloudformation.json') and \
        not options.template_url.endswith('multi-master.cloudformation.json')
    # Required
    options.aws_access_key_id = calculate_environment_variable('AWS_ACCESS_KEY_ID')
    options.aws_secret_access_key = calculate_environment_variable('AWS_SECRET_ACCESS_KEY')

    add_env = []
    prefix = 'TEST_ADD_ENV_'
    for k, v in os.environ.items():
        if k.startswith(prefix):
            add_env.append(k.replace(prefix, '') + '=' + v)
    options.test_cmd = os.getenv('DCOS_PYTEST_CMD', ' '.join(add_env) + ' py.test -vv -rs ' + options.ci_flags)
    return options


def main():
    options = check_environment()
    bw = test_util.aws.BotoWrapper(
        region=options.aws_region,
        aws_access_key_id=options.aws_access_key_id,
        aws_secret_access_key=options.aws_secret_access_key)
    stack_name = 'dcos-ci-test-cf-{}'.format(random_id(10))
    ssh_key = bw.create_key_pair(stack_name)
    write_string('ssh_key', ssh_key)
    log.info('Spinning up AWS CloudFormation with ID: {}'.format(stack_name))
    if options.advanced:
        cf, ssh_info = test_util.aws.DcosZenCfStack.create(
            stack_name=stack_name,
            boto_wrapper=bw,
            template_url=options.template_url,
            private_agents=options.agents,
            public_agents=options.public_agents,
            key_pair_name=stack_name,
            private_agent_type='m4.xlarge',
            public_agent_type='m4.xlarge',
            master_type='m4.xlarge',
            vpc=options.vpc,
            gateway=options.gateway,
            private_subnet=options.private_subnet,
            public_subnet=options.public_subnet)
    else:
        cf, ssh_info = test_util.aws.DcosCfStack.create(
            stack_name=stack_name,
            template_url=options.template_url,
            private_agents=options.agents,
            public_agents=options.public_agents,
            admin_location='0.0.0.0/0',
            key_pair_name=stack_name,
            boto_wrapper=bw)
    time.sleep(300)  # we know the cluster is not ready yet, don't poll to avoid hitting the rate limit
    cf.wait_for_complete()
    # Resiliency testing requires knowing the stack name
    options.test_cmd = 'AWS_STACK_NAME=' + stack_name + ' ' + options.test_cmd

    # hidden hook where user can supply an ssh_key for a preexisting cluster
    cluster = test_util.cluster.Cluster.from_cloudformation(cf, ssh_info, ssh_key)

    result = test_util.cluster.run_integration_tests(
        cluster,
        region=options.aws_region,
        aws_access_key_id=options.aws_access_key_id,
        aws_secret_access_key=options.aws_secret_access_key,
        test_cmd=options.test_cmd,
    )
    if result == 0:
        log.info('Test successful! Deleting CloudFormation.')
        cf.delete()
        bw.delete_key_pair(stack_name)
    else:
        logging.warning('Test exited with an error')
    if options.ci_flags:
        result = 0  # Wipe the return code so that tests can be muted in CI
    sys.exit(result)


if __name__ == '__main__':
    main()
