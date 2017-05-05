import copy
import logging


import launch.util
import test_util.azure
import test_util.runner

log = logging.getLogger(__name__)


class AzureResourceGroupLauncher(launch.util.AbstractLauncher):
    def __init__(self, config: dict):
        self.azure_wrapper = test_util.azure.AzureWrapper(
            config['azure_location'], config['azure_subscription_id'], config['azure_client_id'],
            config['azure_client_secret'], config['azure_tenant_id'])
        self.config = config
        log.debug('Using Azure Resource Group Launcher')

    def create(self):
        self.key_helper()
        self.azure_wrapper.deploy_template_to_new_resource_group(
            self.config['template_url'],
            self.config['deployment_name'],
            self.config['template_parameters'])
        info = copy.deepcopy(self.config)
        return info

    def wait(self):
        self.resource_group.wait_for_deployment()

    def describe(self):
        return {
            'masters': launch.util.convert_host_list(self.resource_group.get_master_ips()),
            'private_agents': launch.util.convert_host_list(self.resource_group.get_private_agent_ips()),
            'public_agents': launch.util.convert_host_list(self.resource_group.get_public_agent_ips()),
            'master_fqdn': self.resource_group.public_master_lb_fqdn,
            'public_agent_fqdn': self.resource_group.public_agent_lb_fqdn}

    def delete(self):
        self.resource_group.delete()

    def key_helper(self):
        """ Adds private key to the config and injects the public key into
        the template parameters
        """
        if self.config['key_helper'] is not True:
            return
        if 'sshRSAPublicKey' in self.config['template_parameters']:
            raise launch.util.LauncherError('KeyHelperError', 'key_helper will automatically'
                                            'calculate and inject sshRSAPublicKey; do not set this parameter')
        private_key, public_key = launch.util.generate_rsa_keypair()
        self.config.update({'ssh_private_key': private_key.decode()})
        self.config['template_parameters'].update({'sshRSAPublicKey': public_key.decode()})

    @property
    def resource_group(self):
        try:
            return test_util.azure.DcosAzureResourceGroup(self.config['deployment_name'], self.azure_wrapper)
        except Exception as ex:
            raise launch.util.LauncherError('GroupNotFound', None) from ex

    def test(self, args: list, env: dict):
        details = self.describe()
        test_host = details['master_fqdn']
        if 'DCOS_DNS_ADDRESS' not in env:
            env['DCOS_DNS_ADDRESS'] = 'http://' + test_host
        return super().test(args, env, test_host=test_host, test_port=2200)
