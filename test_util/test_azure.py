#!/usr/bin/env python3
"""Deploys DC/OS ACS template and then runs the integration test suite

The following environment variables are required:

AZURE_TEMPLATE_URL: string
    The template to be used for deployment testing

DCOS_NAME: string
    Instead of providing a template, supply the name (or id) of an already
    existing cluster

AZURE_PUBLIC_SSH_KEY: string
    public key that Azure hosts will trust for SSH login

AZURE_SUBSCRIPTION_ID
AZURE_TENANT_ID
AZURE_CLIENT_ID
AZURE_CLIENT_SECRET
    These for strings must be set in order to access Azure

The following environment variables are settable, but have workable defaults:

DCOS_SSH_KEY_PATH: string
    path for the private SSH key to be used to log into the cluster

AGENTS: integer (default=2)
    The number of agents to create in a new cluster.

DCOS_NAME: string, (default='testing-' + 10 random lower case characters)
    String that will be used for the Azure Resource Group name that contains this DC/OS

AZURE_LOCATION: string (default='East US')
    Which administrative region the resource group will be launched in

AZURE_LINUX_USER: string (default=dcos)
    Username for the default OS user

AZURE_AGENT_PREFIX: string (default='test-' + 10 random lower case characters)

AZURE_MASTER_PREFIX: string (default='test-' + 10 random lower case characters)

AZURE_VM_SIZE: string (default='Standard_D2')
    One of the specific Azure VM types. See the template for full support list

AZURE_DCOS_SUFFIX: string (default=12345)
    String to be tagged to resources

AZURE_OAUTH_ENABLED: boolean (default=false)
    Control if DC/OS oauth is activated after deploy or not

AZURE_VM_DIAGNOSTICS_ENABLED: boolean (default=true)

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

from gen.calc import calculate_environment_variable
from pkgpanda.util import load_string
from ssh.tunnel import tunnel
from test_util.azure import AzureWrapper, DcosAzureResourceGroup
from test_util.helpers import random_id
from test_util.runner import integration_test

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
logging.getLogger("msrest").setLevel(logging.INFO)
logging.getLogger("requests_oauthlib").setLevel(logging.INFO)
logging.getLogger("requests.packages").setLevel(logging.INFO)
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

    # Required
    options.public_ssh_key = calculate_environment_variable('AZURE_PUBLIC_SSH_KEY')
    options.subscription_id = calculate_environment_variable('AZURE_SUBSCRIPTION_ID')
    options.tenant_id = calculate_environment_variable('AZURE_TENANT_ID')
    options.client_id = calculate_environment_variable('AZURE_CLIENT_ID')
    options.client_secret = calculate_environment_variable('AZURE_CLIENT_SECRET')
    options.template_url = calculate_environment_variable('AZURE_TEMPLATE_URL')

    # Provided if not set
    options.name = os.getenv('DCOS_NAME', 'testing-{}'.format(random_id(10)))
    options.ssh_key_path = os.getenv('DCOS_SSH_KEY_PATH', 'ssh_key')
    options.location = os.getenv('AZURE_LOCATION', 'East US')
    options.linux_user = os.getenv('AZURE_LINUX_USER', 'dcos')
    # Prefixes must not begin with a number
    options.agent_prefix = os.getenv('AZURE_AGENT_PREFIX', 'test' + random_id(10).lower())
    options.master_prefix = os.getenv('AZURE_MASTER_PREFIX', 'test' + random_id(10).lower())
    options.vm_size = os.getenv('AZURE_VM_SIZE', 'Standard_D2')
    options.num_agents = os.getenv('AGENTS', '2')
    options.name_suffix = os.getenv('AZURE_DCOS_SUFFIX', '12345')
    options.oauth_enabled = os.getenv('AZURE_OAUTH_ENABLED', 'true')
    options.vm_diagnostics_enabled = os.getenv('AZURE_VM_DIAGNOSTICS_ENABLED', 'true')
    options.ci_flags = os.getenv('CI_FLAGS', '')

    add_env = []
    prefix = 'TEST_ADD_ENV_'
    for k, v in os.environ.items():
        if k.startswith(prefix):
            add_env.append(k.replace(prefix, '') + '=' + v)
    options.test_cmd = os.getenv(
        'DCOS_PYTEST_CMD', ' '.join(add_env) + " py.test -vv -s -rs -m 'not ccm' " + options.ci_flags)
    return options


def main():
    options = check_environment()
    aw = AzureWrapper(
        options.location,
        options.subscription_id,
        options.client_id,
        options.client_secret,
        options.tenant_id)
    dcos_resource_group = DcosAzureResourceGroup.deploy_acs_template(
        azure_wrapper=aw,
        template_url=options.template_url,
        group_name=options.name,
        public_key=options.public_ssh_key,
        master_prefix=options.master_prefix,
        agent_prefix=options.agent_prefix,
        admin_name=options.linux_user,
        oauth_enabled=options.oauth_enabled,
        vm_size=options.vm_size,
        agent_count=options.num_agents,
        name_suffix=options.name_suffix,
        vm_diagnostics_enabled=options.vm_diagnostics_enabled)
    result = 1
    dcos_resource_group.wait_for_deployment()
    dcos_dns = dcos_resource_group.public_master_lb_fqdn
    master_list = [ip.private_ip for ip in dcos_resource_group.get_master_ips()]
    with tunnel(options.linux_user, load_string(options.ssh_key_path),
                dcos_dns, port=2200) as t:
        result = integration_test(
            tunnel=t,
            dcos_dns=dcos_dns,
            master_list=master_list,
            agent_list=[ip.private_ip for ip in dcos_resource_group.get_private_agent_ips()],
            public_agent_list=[ip.private_ip for ip in dcos_resource_group.get_public_agent_ips()],
            test_cmd=options.test_cmd)
    if result == 0:
        log.info('Test successsful! Deleting Azure resource group')
        dcos_resource_group.delete()
    else:
        logging.warning('Test exited with an error; Resource group preserved for troubleshooting.'
                        'See https://github.com/mesosphere/cloudcleaner project for cleanup policies')
    if options.ci_flags:
        result = 0  # Wipe the return code so that tests can be muted in CI
    sys.exit(result)


if __name__ == '__main__':
    main()
