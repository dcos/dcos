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
    def __init__(self, azure_wrapper: test_util.azure.AzureWrapper):
        self.azure_wrapper = azure_wrapper
        log.debug('Using Azure Resource Group Launcher')

    def create(self, config):
        launch.util.check_keys(config, ['deployment_name', 'template_url'])
        if config['key_helper'] == 'true':
            self.key_helper(config)
        self.azure_wrapper.deploy_template_to_new_resource_group(
            config['template_url'], config['deployment_name'], yaml.load(config['template_parameters']))
        info = copy.deepcopy(config)
        return info

    def wait(self, info):
        self.get_resource_group(info).wait_for_deployment()

    def describe(self, info):
        rg = self.get_resource_group(info)
        return {
            'masters': launch.util.convert_host_list(rg.get_master_ips()),
            'private_agents': launch.util.convert_host_list(rg.get_private_agent_ips()),
            'public_agents': launch.util.convert_host_list(rg.get_public_agent_ips()),
            'master_fqdn': rg.public_master_lb_fqdn,
            'public_agent_fqdn': rg.public_agent_lb_fqdn}

    def delete(self, info):
        self.get_resource_group(info).delete()

    def key_helper(self, config):
        """ Adds private key to the config and injects the public key into
        the template parameters
        """
        private_key, public_key = launch.util.generate_rsa_keypair()
        config.update({'ssh_private_key': private_key.decode()})
        template_parameters = yaml.load(config['template_parameters'])
        template_parameters.update({'sshRSAPublicKey': public_key.decode()})
        config['template_parameters'] = yaml.dump(template_parameters)

    def get_resource_group(self, info):
        try:
            return test_util.azure.DcosAzureResourceGroup(info['deployment_name'], self.azure_wrapper)
        except Exception as ex:
            raise launch.util.LauncherError('GroupNotFound', None) from ex

    def test(self, info, test_cmd):
        launch.util.check_testable(info)
        details = self.describe(info)
        test_host = details['master_fqdn']
        with ssh.tunnel.tunnel(info['ssh_user'], info['ssh_private_key'], test_host, port=2200) as test_tunnel:
            return test_util.runner.integration_test(
                tunnel=test_tunnel,
                dcos_dns=test_host,
                master_list=[m['private_ip'] for m in details['masters']],
                agent_list=[a['private_ip'] for a in details['private_agents']],
                public_agent_list=[a['private_ip'] for a in details['public_agents']],
                test_cmd=test_cmd)
