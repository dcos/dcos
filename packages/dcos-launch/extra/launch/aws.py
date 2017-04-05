import copy
import logging

import yaml

import launch.util
import ssh.tunnel
import test_util.aws
import test_util.runner

log = logging.getLogger(__name__)


class AwsCloudformationLauncher(launch.util.AbstractLauncher):
    def __init__(self, boto_wrapper: test_util.aws.BotoWrapper):
        self.boto_wrapper = boto_wrapper
        log.debug('Using AWS Cloudformation Launcher')

    def create(self, config):
        """ Checks if the key helper or zen helper are enabled,
        provides resources according to those helpers, tracking which resources
        were created, and then attempts to deploy the template.

        Note: both key helper and zen helper will mutate the config to inject
        the appropriate template parameters for the generated resources
        """
        launch.util.check_keys(config, ['deployment_name', 'template_url'])
        temp_resources = {}
        if config['key_helper'] == 'true':
            temp_resources.update(self.key_helper(config))
        if config['zen_helper'] == 'true':
            temp_resources.update(self.zen_helper(config))
        try:
            stack = self.boto_wrapper.create_stack(
                config['deployment_name'],
                yaml.load(config['template_parameters']),
                template_url=config['template_url'])
        except Exception as ex:
            self.delete_temp_resources(temp_resources)
            raise launch.util.LauncherError('ProviderError', None) from ex
        info = copy.deepcopy(config)
        info.update({
            'stack_id': stack.stack_id,
            'temp_resources': temp_resources})
        return info

    def zen_helper(self, config):
        """
        Checks parameters for Zen template prerequisites are met. If not met, they
        will be provided (must be done in correct order) and added to the info
        JSON as 'temp_resources'
        """
        parameters = yaml.load(config['template_parameters'])
        temp_resources = {}
        if 'Vpc' not in parameters:
            vpc_id = self.boto_wrapper.create_vpc_tagged('10.0.0.0/16', config['deployment_name'])
            parameters['Vpc'] = vpc_id
            temp_resources['vpc'] = vpc_id
        if 'InternetGateway' not in parameters:
            gateway_id = self.boto_wrapper.create_internet_gateway_tagged(vpc_id, config['deployment_name'])
            parameters['InternetGateway'] = gateway_id
            temp_resources.update({'gateway': gateway_id})
        if 'PrivateSubnet' not in parameters:
            private_subnet_id = self.boto_wrapper.create_subnet_tagged(
                vpc_id, '10.0.0.0/17', config['deployment_name'] + 'private')
            parameters['PrivateSubnet'] = private_subnet_id
            temp_resources.update({'private_subnet': private_subnet_id})
        if 'PublicSubnet' not in parameters:
            public_subnet_id = self.boto_wrapper.create_subnet_tagged(
                vpc_id, '10.0.128.0/20', config['deployment_name'] + '-public')
            parameters['PublicSubnet'] = public_subnet_id
            temp_resources.update({'public_subnet': public_subnet_id})
        config['template_parameters'] = yaml.dump(parameters)
        return temp_resources

    def wait(self, info):
        self.get_stack(info).wait_for_complete()

    def describe(self, info):
        cf = self.get_stack(info)
        return {
            'masters': launch.util.convert_host_list(cf.get_master_ips()),
            'private_agents': launch.util.convert_host_list(cf.get_private_agent_ips()),
            'public_agents': launch.util.convert_host_list(cf.get_public_agent_ips())}

    def delete(self, info):
        stack = self.get_stack(info)
        stack.delete()
        if len(info['temp_resources']) > 0:
            # must wait for stack to be deleted before removing
            # network resources on which it depends
            stack.wait_for_complete()
            self.delete_temp_resources(info['temp_resources'])

    def delete_temp_resources(self, temp_resources):
        if 'key_name' in temp_resources:
            self.boto_wrapper.delete_key_pair(temp_resources['key_name'])
        if 'public_subnet' in temp_resources:
            self.boto_wrapper.delete_subnet(temp_resources['public_subnet'])
        if 'private_subnet' in temp_resources:
            self.boto_wrapper.delete_subnet(temp_resources['private_subnet'])
        if 'gateway' in temp_resources:
            self.boto_wrapper.delete_internet_gateway(temp_resources['gateway'])
        if 'vpc' in temp_resources:
            self.boto_wrapper.delete_vpc(temp_resources['vpc'])

    def key_helper(self, config):
        key_name = config['deployment_name']
        private_key = self.boto_wrapper.create_key_pair(key_name)
        config.update({'ssh_private_key': private_key})
        template_parameters = yaml.load(config['template_parameters'])
        template_parameters.update({'KeyName': key_name})
        config['template_parameters'] = yaml.dump(template_parameters)
        return {'key_name': key_name}

    def get_stack(self, info):
        try:
            return test_util.aws.fetch_stack(info['stack_id'], self.boto_wrapper)
        except Exception as ex:
            raise launch.util.LauncherError('StackNotFound', None) from ex

    def test(self, info, test_cmd):
        launch.util.check_testable(info)
        details = self.describe(info)
        test_host = details['masters'][0]['public_ip']
        with ssh.tunnel.tunnel(info['ssh_user'], info['ssh_private_key'], test_host) as test_tunnel:
            return test_util.runner.integration_test(
                tunnel=test_tunnel,
                dcos_dns=test_host,
                master_list=[m['private_ip'] for m in details['masters']],
                agent_list=[a['private_ip'] for a in details['private_agents']],
                public_agent_list=[a['private_ip'] for a in details['public_agents']],
                aws_access_key_id=info['aws_access_key_id'],
                aws_secret_access_key=info['aws_secret_access_key'],
                region=info['aws_region'],
                test_cmd=test_cmd)
