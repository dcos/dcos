import copy
import logging

import yaml

import launch.util
import ssh.tunnel
import test_util.aws
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
        launch.util.check_keys(self.config, ['deployment_name', 'template_url'])
        if self.config['key_helper'] == 'true':
            self.key_helper()
        self.azure_wrapper.deploy_template_to_new_resource_group(
            self.config['template_url'],
            self.config['deployment_name'],
            yaml.load(self.config['template_parameters']))
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
        private_key, public_key = launch.util.generate_rsa_keypair()
        self.config.update({'ssh_private_key': private_key.decode()})
        template_parameters = yaml.load(self.config['template_parameters'])
        template_parameters.update({'sshRSAPublicKey': public_key.decode()})
        self.config['template_parameters'] = yaml.dump(template_parameters)

    @property
    def resource_group(self):
        try:
            return test_util.azure.DcosAzureResourceGroup(self.config['deployment_name'], self.azure_wrapper)
        except Exception as ex:
            raise launch.util.LauncherError('GroupNotFound', None) from ex

    def test(self, test_cmd):
        launch.util.check_testable(self.config)
        details = self.describe()
        test_host = details['master_fqdn']
        master_private_ips = [m['private_ip'] for m in details['masters']]
        with ssh.tunnel.tunnel(
                self.config['ssh_user'], self.config['ssh_private_key'], test_host, port=2200) as test_tunnel:
            return test_util.runner.integration_test(
                tunnel=test_tunnel,
                # DCOS-14627 [azure] route port 80 and 443 to master via master public LB if oauth enbaled
                # ACS templates do not have inbound NAT rules or NSG rules for the public LB address
                # Thus, use the private IP instead.
                dcos_dns=master_private_ips[0],
                master_list=master_private_ips,
                agent_list=[a['private_ip'] for a in details['private_agents']],
                public_agent_list=[a['private_ip'] for a in details['public_agents']],
                test_cmd=test_cmd)
