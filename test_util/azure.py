import contextlib
import logging
import re
from typing import Union

import azure.common.credentials
from azure.common.exceptions import CloudError
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource.resources import ResourceManagementClient
from azure.mgmt.resource.resources.models import (DeploymentMode,
                                                  DeploymentProperties,
                                                  ResourceGroup, TemplateLink)
from retrying import retry

from test_util.helpers import lazy_property


# Very noisy loggers that do not help much in debug mode
logging.getLogger("msrest").setLevel(logging.INFO)
logging.getLogger("requests_oauthlib").setLevel(logging.INFO)
log = logging.getLogger(__name__)

# This interface is designed to only use a single deployment
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


class AzureWrapper:
    def __init__(self, subscription_id: str, client_id: str, client_secret: str, tenant_id: str):
        self.credentials = azure.common.credentials.ServicePrincipalCredentials(
            client_id=client_id,
            secret=client_secret,
            tenant=tenant_id)
        self.rmc = ResourceManagementClient(self.credentials, subscription_id)
        self.nmc = NetworkManagementClient(self.credentials, subscription_id)


class DcosAzureResourceGroup:
    def __init__(self, group_name, azure_wrapper):
        self.group_name = group_name
        self.azure_wrapper = azure_wrapper

    @classmethod
    def deploy_acs_template(
            cls, azure_wrapper, template_uri, location, group_name,
            public_key, master_prefix, agent_prefix, admin_name, oauth_enabled: Union[bool, str],
            vm_size, agent_count, name_suffix, vm_diagnostics_enabled: bool):
        """ Creates a new resource group and deploys a ACS DC/OS template to it
        """
        assert master_prefix != agent_prefix, 'Master and agents must have unique prefixs'
        validate_hostname_prefix(master_prefix)
        validate_hostname_prefix(agent_prefix)

        deployment_name = DEPLOYMENT_NAME.format(group_name)

        # Resource group must be created before validation can occur
        if azure_wrapper.rmc.resource_groups.check_existence(group_name):
            raise Exception("Group name already exists / taken: {}".format(group_name))
        log.info('Starting resource group_creation')
        with contextlib.ExitStack() as stack:
            azure_wrapper.rmc.resource_groups.create_or_update(
                group_name,
                ResourceGroup(location=location))
            stack.callback(azure_wrapper.rmc.resource_groups.delete, group_name)
            log.info('Resource group created: {}'.format(group_name))

            template_params = {
                'sshRSAPublicKey': public_key,
                # must be lower or validation will fail
                'masterEndpointDNSNamePrefix': master_prefix,
                'agentEndpointDNSNamePrefix': agent_prefix,
                'linuxAdminUsername': admin_name,
                'agentVMSize': vm_size,
                'agentCount': agent_count,
                'nameSuffix': name_suffix,
                'oauthEnabled': repr(oauth_enabled).lower(),
                # oauth uses string, vm diagnostic uses bool
                'enableVMDiagnostics': vm_diagnostics_enabled}
            log.info('Provided template parameters: {}'.format(template_params))
            # azure requires that parameters be provided as {key: {'value': value}}
            template_parameters = {k: {'value': v} for k, v in template_params.items()}
            deployment_properties = DeploymentProperties(
                template_link=TemplateLink(uri=template_uri),
                mode=DeploymentMode.incremental,
                parameters=template_parameters)
            log.info('Checking with Azure to validate template deployment')
            result = azure_wrapper.rmc.deployments.validate(
                group_name, deployment_name, properties=deployment_properties)
            if result.error:
                for details in result.error.details:
                    log.error('{}: {}'.format(details.code, details.message))
                error_msgs = '\n'.join(['{}: {}'.format(d.code, d.message) for d in result.error.details])
                raise Exception("Template verification failed!\n{}".format(error_msgs))
            log.info('Template successfully validated')
            log.info('Starting template deployment')
            azure_wrapper.rmc.deployments.create_or_update(
                group_name, deployment_name, deployment_properties)
            stack.pop_all()
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

        @retry(wait_fixed=60 * 1000, stop_max_delay=timeout * 1000,
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

    def get_ip_buckets(self):
        """ Go through all network interfaces for this resource group and grab
        the correct IP by matching a sting in the resource name
        """
        # FIXME: sometimes this method returns nodes that shouldn't exist as part of the cluster
        #        it is not clear what the issue is, but it might be 'magic' provisioning interfaces
        ip_buckets = {
            'master': [],
            'private': [],
            'public': []}
        for resource in self.azure_wrapper.rmc.resource_groups.list_resources(
                self.group_name,
                filter=("resourceType eq 'Microsoft.Network/networkInterfaces' or "
                        "resourceType eq 'Microsoft.Compute/virtualMachineScaleSets'")):
            if resource.type == 'Microsoft.Network/networkInterfaces':
                nics = [self.azure_wrapper.nmc.network_interfaces.get(self.group_name, resource.name)]
            elif resource.type == 'Microsoft.Compute/virtualMachineScaleSets':
                nics = list(self.azure_wrapper.nmc.network_interfaces.list_virtual_machine_scale_set_network_interfaces(
                    virtual_machine_scale_set_name=resource.name, resource_group_name=self.group_name))
            else:
                raise('Unexpected resourceType: {}'.format(resource.type))

            for bucket_name in ip_buckets:
                if bucket_name in resource.name:
                    for n in nics:
                        for config in n.ip_configurations:
                            ip_buckets[bucket_name].append(config.private_ip_address)
        return ip_buckets

    @lazy_property
    def ip_buckets(self):
        return self.get_ip_buckets()

    def get_outputs(self):
        return {k: v['value'] for k, v in self.azure_wrapper.rmc.deployments.
                get(self.group_name, DEPLOYMENT_NAME.format(self.group_name)).properties.outputs.items()}

    @lazy_property
    def outputs(self):
        return self.get_outputs()

    def get_master_ips(self):
        return self.ip_buckets['master']

    def get_public_ips(self):
        return self.ip_buckets['public']

    def get_private_ips(self):
        return self.ip_buckets['private']

    def delete(self):
        log.info('Triggering delete')
        self.azure_wrapper.rmc.resource_groups.delete(self.group_name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, exc_tb):
        self.delete()
