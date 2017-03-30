import copy
import logging

import yaml

import launch.util
import test_util.aws
import test_util.runner

log = logging.getLogger(__name__)


class DcosCloudformationLauncher(launch.util.AbstractLauncher):
    def __init__(self, config: dict):
        self.boto_wrapper = test_util.aws.BotoWrapper(
            config['aws_region'], config['aws_access_key_id'], config['aws_secret_access_key'])
        self.config = config
        log.debug('Using AWS Cloudformation Launcher')

    def create(self):
        """ Checks if the key helper or zen helper are enabled,
        provides resources according to those helpers, tracking which resources
        were created, and then attempts to deploy the template.

        Note: both key helper and zen helper will mutate the config to inject
        the appropriate template parameters for the generated resources
        """
        temp_resources = {}
        temp_resources.update(self.key_helper())
        temp_resources.update(self.zen_helper())
        try:
            stack = self.boto_wrapper.create_stack(
                self.config['deployment_name'],
                yaml.load(self.config['template_parameters']),
                template_url=self.config.get('template_url'),
                template_body=self.config.get('template_body'))
        except Exception as ex:
            self.delete_temp_resources(temp_resources)
            raise launch.util.LauncherError('ProviderError', None) from ex
        info = copy.deepcopy(self.config)
        info.update({
            'stack_id': stack.stack_id,
            'temp_resources': temp_resources})
        return info

    def zen_helper(self):
        """
        Checks parameters for Zen template prerequisites are met. If not met, they
        will be provided (must be done in correct order) and added to the info
        JSON as 'temp_resources'
        """
        if self.config['zen_helper'] != 'true':
            return {}
        parameters = yaml.load(self.config['template_parameters'])
        temp_resources = {}
        if 'Vpc' not in parameters:
            vpc_id = self.boto_wrapper.create_vpc_tagged('10.0.0.0/16', self.config['deployment_name'])
            parameters['Vpc'] = vpc_id
            temp_resources['vpc'] = vpc_id
        if 'InternetGateway' not in parameters:
            gateway_id = self.boto_wrapper.create_internet_gateway_tagged(vpc_id, self.config['deployment_name'])
            parameters['InternetGateway'] = gateway_id
            temp_resources.update({'gateway': gateway_id})
        if 'PrivateSubnet' not in parameters:
            private_subnet_id = self.boto_wrapper.create_subnet_tagged(
                vpc_id, '10.0.0.0/17', self.config['deployment_name'] + 'private')
            parameters['PrivateSubnet'] = private_subnet_id
            temp_resources.update({'private_subnet': private_subnet_id})
        if 'PublicSubnet' not in parameters:
            public_subnet_id = self.boto_wrapper.create_subnet_tagged(
                vpc_id, '10.0.128.0/20', self.config['deployment_name'] + '-public')
            parameters['PublicSubnet'] = public_subnet_id
            temp_resources.update({'public_subnet': public_subnet_id})
        self.config['template_parameters'] = yaml.dump(parameters)
        return temp_resources

    def wait(self):
        self.stack.wait_for_complete()

    def describe(self):
        return {
            'masters': launch.util.convert_host_list(self.stack.get_master_ips()),
            'private_agents': launch.util.convert_host_list(self.stack.get_private_agent_ips()),
            'public_agents': launch.util.convert_host_list(self.stack.get_public_agent_ips())}

    def delete(self):
        self.stack.delete()
        if len(self.config['temp_resources']) > 0:
            # must wait for stack to be deleted before removing
            # network resources on which it depends
            self.stack.wait_for_complete()
            self.delete_temp_resources(self.config['temp_resources'])

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

    def key_helper(self):
        """ If key_helper is true, then create an EC2 keypair with the same name
        as the cloudformation stack, update the config with the resulting private key,
        and amend the cloudformation template parameters to have KeyName set as this key
        """
        if self.config['key_helper'] != 'true':
            return {}
        key_name = self.config['deployment_name']
        private_key = self.boto_wrapper.create_key_pair(key_name)
        self.config.update({'ssh_private_key': private_key})
        template_parameters = yaml.load(self.config['template_parameters'])
        template_parameters.update({'KeyName': key_name})
        self.config['template_parameters'] = yaml.dump(template_parameters)
        return {'key_name': key_name}

    @property
    def stack(self):
        try:
            return test_util.aws.fetch_stack(self.config['stack_id'], self.boto_wrapper)
        except Exception as ex:
            raise launch.util.LauncherError('StackNotFound', None) from ex


class BareClusterLauncher(DcosCloudformationLauncher):
    """ Launches a homogenous cluster of plain AMIs intended for onprem DC/OS
    """
    def create(self):
        """ Amend the config to add a template_body and the appropriate parameters
        """
        self.config.update({
            'template_body': test_util.aws.template_by_instance_type(self.config['instance_type']),
            'template_parameters': yaml.dump({
                'KeyName': self.config['aws_key_name'],
                'AllowAccessFrom': self.config['admin_location'],
                'ClusterSize': self.config['cluster_size'],
                'InstanceType': self.config['instance_type'],
                'AmiCode': self.config['instance_ami']})})
        return super().create()

    def get_hosts(self):
        return self.stack.get_host_ips()

    def describe(self):
        return {'host_list': launch.util.convert_host_list(self.get_hosts())}

    def test(self, args, env):
        raise NotImplementedError('Bare clusters cannot be tested!')
