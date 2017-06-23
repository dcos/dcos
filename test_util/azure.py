""" This module is intended to allow deploying of arbitrary Azure Resource
Manager templates. For more information on how to configure and interpret these
templates, see:

https://docs.microsoft.com/en-us/azure/azure-resource-manager/resource-group-authoring-templates
"""
import contextlib
import copy
import logging
import re

import requests
import retrying
from azure.common.credentials import ServicePrincipalCredentials
from azure.common.exceptions import CloudError
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource.resources import ResourceManagementClient
from azure.mgmt.resource.resources.models import (DeploymentMode,
                                                  DeploymentProperties,
                                                  ResourceGroup)

from test_util.helpers import Host

log = logging.getLogger(__name__)

# This interface is designed to only use a single deployment.
# Being as the azure interface is based around resource groups, deriving
# deployment name from group names makes it easier to attach to creating deploys
DEPLOYMENT_NAME = '{}-Deployment'


def validate_hostname_prefix(prefix):
    """Hostname prefixes in azure templates are used to link a variety of resources
    Not all of these resources will have their constraints checked at when ARM
    valiation occurs. This check in particular was aggravating as no docs surfaced
    this issue, so logs needed to be scanned just to discover this error
    """
    assert re.match('^[a-z][a-z0-9-]{1,61}[a-z0-9]$', prefix), 'Invalid DNS prefix: {}'.format(prefix)


def check_json_object(obj):
    """ Simple check to fill in the map for automatic parameter casting
    JSON objects must be represented as dict at this level
    """
    assert isinstance(obj, dict), 'Invalid JSON object: {}'.format(obj)
    return obj


def check_array(arr):
    """ Simple check to fill in the map for automatic parameter casting
    JSON arrays must be represented as lists at this level
    """
    assert isinstance(arr, list), 'Invalid array: {}'.format(arr)
    return arr


def nic_to_host(nic):
    assert len(nic.ip_configurations) == 1
    ip_config = nic.ip_configurations[0]
    if ip_config.public_ip_address is None:
        return Host(ip_config.private_ip_address, None)
    return Host(ip_config.private_ip_address, ip_config.public_ip_address.ip_address)


class AzureWrapper:
    def __init__(self, location: str, subscription_id: str, client_id: str, client_secret: str, tenant_id: str):
        self.credentials = ServicePrincipalCredentials(
            client_id=client_id,
            secret=client_secret,
            tenant=tenant_id)
        self.rmc = ResourceManagementClient(self.credentials, subscription_id)
        self.nmc = NetworkManagementClient(self.credentials, subscription_id)
        # location is included to keep a similar model as test_util.aws.BotoWrapper
        self.location = location

    def deploy_template_to_new_resource_group(self, template_url, group_name, parameters):
        log.info('Checking deployment parameters vs template before starting...')
        deployment_properties = self.create_deployment_properties(
            template_url, parameters)
        deployment_name = DEPLOYMENT_NAME.format(group_name)
        # Resource group must be created before validation can occur
        if self.rmc.resource_groups.check_existence(group_name):
            raise Exception("Group name already exists / taken: {}".format(group_name))
        log.info('Starting resource group_creation')

        def get_all_details(error):
            formatted_message = '{}: {}\n\n'.format(error.code, error.message)
            if error.details is None:
                return formatted_message
            for d in error.details:
                formatted_message += get_all_details(d)
            return formatted_message

        with contextlib.ExitStack() as stack:
            self.rmc.resource_groups.create_or_update(
                group_name,
                ResourceGroup(location=self.location))
            # Ensure the resource group will be deleted if the following steps fail
            stack.callback(self.rmc.resource_groups.delete, group_name)
            log.info('Resource group created: {}'.format(group_name))
            log.info('Checking with Azure to validate template deployment')
            result = self.rmc.deployments.validate(
                group_name, deployment_name, properties=deployment_properties)
            if result.error:
                raise Exception("Template verification failed!\n{}".format(get_all_details(result.error)))
            log.info('Template successfully validated')
            log.info('Starting template deployment')
            self.rmc.deployments.create_or_update(
                group_name, deployment_name, deployment_properties, raw=True)
            stack.pop_all()
        log.info('Successfully started template deployment')

    def create_deployment_properties(self, template_url, parameters):
        """ Pulls the targeted template, checks parameter specs and casts
        user provided parameters to the appropriate type. Assertion is raised
        if there are unused parameters or invalid casting
        """
        user_parameters = copy.deepcopy(parameters)
        type_cast_map = {
            'string': str,
            'secureString': str,
            'int': int,
            'bool': bool,
            'object': check_json_object,
            'secureObject': check_json_object,
            'array': check_array}
        log.debug('Pulling Azure template for parameter validation...')
        r = requests.get(template_url)
        r.raise_for_status()
        template = r.json()
        if 'parameters' not in template:
            assert user_parameters is None, 'This template does not support parameters, ' \
                'yet parameters were supplied: {}'.format(user_parameters)
        log.debug('Constructing DeploymentProperties from user parameters: {}'.format(parameters))
        template_parameters = {}
        for k, v in template['parameters'].items():
            if k in user_parameters:
                # All templates parameters are required to have a type field.
                # Azure requires that parameters be provided as {key: {'value': value}}.
                template_parameters[k] = {
                    'value': type_cast_map[v['type']](user_parameters.pop(k))}
        log.debug('Final template parameters: {}'.format(template_parameters))
        if len(user_parameters) > 0:
            raise Exception('Unrecognized template parameters were supplied: {}'.format(user_parameters))
        return DeploymentProperties(
            template=template,
            mode=DeploymentMode.incremental,
            parameters=template_parameters)


class DcosAzureResourceGroup:
    """ An abstraction for cleanly handling the life cycle of a DC/OS template
    deployment. Operations include: create, wait, describe host IPs, and delete
    """
    def __init__(self, group_name, azure_wrapper):
        self.group_name = group_name
        self.azure_wrapper = azure_wrapper

    @classmethod
    def deploy_acs_template(
            cls, azure_wrapper: AzureWrapper, template_url: str, group_name: str,
            public_key, master_prefix, agent_prefix, admin_name, oauth_enabled,
            vm_size, agent_count, name_suffix, vm_diagnostics_enabled):
        """ Creates a new resource group and deploys a ACS DC/OS template to it
        using a subset of parameters for a simple deployment. To see a full
        listing of parameters, including description and formatting, go to:
        gen/azure/templates/acs.json in this repository.

        Args:
            azure_wrapper: see above
            template_url: Azure-accessible location for the desired ACS template
            group_name: name used for the new resource group that will be created
                for this template deployment

        Args that wrap template parameters:
            public_key -> sshRSAPublicKey
            master_prefix -> masterEndpointDNSNamePrefix
            agent_prefix -> agentEndpointDNSNamePrefix
            admin_name -> linuxAdminUsername
            vm_size -> agentVMSize
            agent_count -> agentCount
            name_suffix -> nameSuffix
            oauth_enabled -> oauthEnabled
            vm_diagnostics_enabled -> enableVMDiagnostics
        """
        assert master_prefix != agent_prefix, 'Master and agents must have unique prefixs'
        validate_hostname_prefix(master_prefix)
        validate_hostname_prefix(agent_prefix)

        parameters = {
            'sshRSAPublicKey': public_key,
            'masterEndpointDNSNamePrefix': master_prefix,
            'agentEndpointDNSNamePrefix': agent_prefix,
            'linuxAdminUsername': admin_name,
            'agentVMSize': vm_size,
            'agentCount': agent_count,
            'nameSuffix': name_suffix,
            'oauthEnabled': oauth_enabled,
            'enableVMDiagnostics': vm_diagnostics_enabled}
        azure_wrapper.deploy_template_to_new_resource_group(template_url, group_name, parameters)
        return cls(group_name, azure_wrapper)

    def wait_for_deployment(self, timeout=45 * 60):
        """
        Azure will not register a template instantly after deployment, so
        CloudError must be expected as retried. Once the ops are retrieved, this
        loops through all operations in the group's only deployment
        if any operations are still in progress, then this function will sleep
        once all operations are complete, if there any failures, those will be
        printed to the log stream
        """
        log.info('Waiting for deployment to finish')

        @retrying.retry(
            wait_fixed=60 * 1000, stop_max_delay=timeout * 1000,
            retry_on_result=lambda res: res is False,
            retry_on_exception=lambda ex: isinstance(ex, CloudError))
        def check_deployment_operations():
            deploy_state = self.azure_wrapper.rmc.deployments.get(
                self.group_name, DEPLOYMENT_NAME.format(self.group_name)).properties.provisioning_state
            if deploy_state == 'Succeeded':
                return True
            elif deploy_state == 'Failed':
                log.info('Deployment failed. Checking deployment operations...')
                deploy_ops = self.azure_wrapper.rmc.deployment_operations.list(
                    self.group_name, DEPLOYMENT_NAME.format(self.group_name))
                failures = [(op.properties.status_code, op.properties.status_message) for op
                            in deploy_ops if op.properties.provisioning_state == 'Failed']
                for failure in failures:
                    log.error('Deployment operation failed! {}: {}'.format(*failure))
                raise Exception('Deployment Failed!')
            else:
                log.info('Waiting for deployment. Current state: {}'.format(deploy_state))
                return False

        check_deployment_operations()

    def list_resources(self, filter_string):
        yield from self.azure_wrapper.rmc.resource_groups.list_resources(
            self.group_name, filter=(filter_string))

    def get_scale_set_nics(self, name_substring):
        for resource in self.list_resources("resourceType eq 'Microsoft.Compute/virtualMachineScaleSets'"):
            if name_substring not in resource.name:
                continue
            yield from self.azure_wrapper.nmc.network_interfaces.list_virtual_machine_scale_set_network_interfaces(
                self.group_name, resource.name)

    def get_public_ip_address(self, name_substring):
        for resource in self.list_resources("resourceType eq 'Microsoft.Network/publicIPAddresses'"):
            if name_substring not in resource.name:
                continue
            return self.azure_wrapper.nmc.public_ip_addresses.get(self.group_name, resource.name)

    @property
    def public_agent_lb_fqdn(self):
        return self.get_public_ip_address('agent-ip').dns_settings.fqdn

    @property
    def public_master_lb_fqdn(self):
        return self.get_public_ip_address('master-ip').dns_settings.fqdn

    @property
    def master_nics(self):
        """ The only instances of networkInterface Resources are for masters
        """
        for resource in self.list_resources("resourceType eq 'Microsoft.Network/networkInterfaces'"):
            assert 'master' in resource.name, 'Expected to only find master NICs, not: {}'.format(resource.name)
            yield self.azure_wrapper.nmc.network_interfaces.get(self.group_name, resource.name)

    def get_master_ips(self):
        """ Traffic from abroad is routed to a master wth the public master
        loadbalancer FQDN and the VM index plus 2200 (so the first master will be at 2200)
        """
        public_lb_ip = self.public_master_lb_fqdn
        return [Host(nic_to_host(nic).private_ip, '{}:{}'.format(public_lb_ip, 2200 + int(nic.name[-1])))
                for nic in self.master_nics]

    def get_private_agent_ips(self):
        return [nic_to_host(nic) for nic in self.get_scale_set_nics('private')]

    def get_public_agent_ips(self):
        """ public traffic is routed to public agents via a specific load balancer """
        public_lb_ip = self.public_agent_lb_fqdn
        return [Host(nic_to_host(nic).private_ip, public_lb_ip)
                for nic in self.get_scale_set_nics('public')]

    def delete(self):
        log.info('Triggering delete')
        self.azure_wrapper.rmc.resource_groups.delete(self.group_name, raw=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, exc_tb):
        self.delete()
