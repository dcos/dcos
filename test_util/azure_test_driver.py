#!/usr/bin/env python3
import os
import random
import sys
import traceback
import uuid

import azure.common.credentials
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource.resources import ResourceManagementClient
from azure.mgmt.resource.resources.models import (DeploymentMode,
                                                  DeploymentProperties,
                                                  ResourceGroup, TemplateLink)
from retrying import retry

import pkgpanda.util
from ssh.tunnel import tunnel
from test_util.runner import integration_test


def validate_env():
    '''
    The following environment variables must be set to ensure the template can be deployed successfully and that
    parameters we rely on from a testing perspective are explicitly set and not relying on defaults which may change.
    '''
    required = [
        'AZURE_PARAM_agentEndpointDNSNamePrefix',
        'AZURE_PARAM_linuxAdminUsername',
        'AZURE_PARAM_masterEndpointDNSNamePrefix',
        'AZURE_PARAM_sshRSAPublicKey',
        'AZURE_TEMPLATE_URL'
    ]
    values = {}
    for k in required:
        assert os.getenv(k), "Environment variable {} must be set".format(k)
        values[k] = os.getenv(k)

    assert values['AZURE_PARAM_masterEndpointDNSNamePrefix'] != values['AZURE_PARAM_agentEndpointDNSNamePrefix'], \
        "Master and agent prefix must be unique"


def get_env_params():
    '''
    Return ARM input template parameters populated based on environment variables. Parameters are set as follows:
      * AZURE_PARAM_key=value (value treated as a string)
      * AZURE_PARAM_INT_key=value (value treated as an int)
    '''
    template_params = {}
    for env_key, env_val in os.environ.items():
        def extract_env_param(name, transform):
            if env_key.startswith(name):
                template_params[env_key[len(name):]] = {'value': transform(env_val)}
                return True
        if extract_env_param('AZURE_PARAM_INT_', int):
            continue
        extract_env_param('AZURE_PARAM_', lambda x: x)
    return(template_params)


def get_value(template_parameter):
    return(get_env_params()[template_parameter]['value'])


def get_test_config():
    add_env = {}
    prefix = 'TEST_ADD_ENV_'
    for k, v in os.environ.items():
        if k.startswith(prefix):
            add_env[k.replace(prefix, '')] = v
    return add_env


def main():
    validate_env()
    location = os.getenv('AZURE_LOCATION', 'East US')
    credentials = azure.common.credentials.ServicePrincipalCredentials(
        client_id=os.environ['AZURE_CLIENT_ID'],
        secret=os.environ['AZURE_CLIENT_SECRET'],
        tenant=os.environ['AZURE_TENANT_ID'])
    subscription_id = os.environ['AZURE_SUBSCRIPTION_ID']
    template = TemplateLink(uri=os.environ['AZURE_TEMPLATE_URL'])
    # tenant_id = os.environ.get('AZURE_TENANT_ID')
    # client_id = os.environ.get('AZURE_CLIENT_ID')
    # client_secret = os.environ.get('AZURE_CLIENT_SECRET')
    group_name = 'testing' + ''.join(random.choice('01234567890abcdef') for n in range(10))
    deployment_name = 'deployment{}'.format(uuid.uuid4().hex)

    rmc = ResourceManagementClient(credentials, subscription_id)

    template_parameters = get_env_params()

    # Output resource group
    print("Resource group name: {}".format(group_name))
    print("Deployment name: {}".format(deployment_name))

    azure_cluster = {
        'resource_group_name': group_name,
        'deployment_name': deployment_name}
    pkgpanda.util.write_json('azure-cluster.json', azure_cluster)

    # Create a new resource group
    print("Creating new resource group in location: {}".format(location))
    if rmc.resource_groups.check_existence(group_name):
        print("ERROR: Group name already exists / taken: {}".format(group_name))
    rmc.resource_groups.create_or_update(
        group_name,
        ResourceGroup(location=location))

    test_successful = False

    try:
        deployment_properties = DeploymentProperties(
            template_link=template,
            mode=DeploymentMode.incremental,
            parameters=template_parameters)

        # Use RPC against azure to validate the ARM template is well-formed
        result = rmc.deployments.validate(group_name, deployment_name, properties=deployment_properties)
        if result.error:
            print("Template verification failed\n{}".format(result.error), file=sys.stderr)
            sys.exit(1)

        # Actually create a template deployment
        print("Creating template deployment ...")
        deploy_poller = rmc.deployments.create_or_update(group_name, deployment_name, deployment_properties)

        # Stop after 45 attempts (each one takes up to one minute)
        @retry(stop_max_attempt_number=45)
        def poll_deploy():
            res = deploy_poller.result(timeout=60)
            print("Current deploy state: {}".format(res.properties.provisioning_state))
            assert deploy_poller.done(), "Not done deploying."

        print("Waiting for template to deploy ...")
        try:
            poll_deploy()
        except:
            print("Current deploy status:\n{}".format(deploy_poller.result(0)))
            raise
        print("Template deployed successfully")

        assert deploy_poller.done(), "Deployment failed / polling didn't reach deployment done."
        deployment_result = deploy_poller.result()
        print(deployment_result.properties.outputs)
        master_lb = deployment_result.properties.outputs['masterFQDN']['value']

        print("Template deployed using SSH private key: https://mesosphere.onelogin.com/notes/18444")
        print("For troubleshooting, master0 can be reached using: ssh -p 2200 {}@{}".format(
            get_value('linuxAdminUsername'), master_lb))

        # Run test now, so grab IPs
        nmc = NetworkManagementClient(credentials, subscription_id)
        ip_buckets = {
            'master': [],
            'private': [],
            'public': []}

        for resource in rmc.resource_groups.list_resources(
                group_name, filter=("resourceType eq 'Microsoft.Network/networkInterfaces' or "
                                    "resourceType eq 'Microsoft.Compute/virtualMachineScaleSets'")):
            if resource.type == 'Microsoft.Network/networkInterfaces':
                nics = [nmc.network_interfaces.get(group_name, resource.name)]
            elif resource.type == 'Microsoft.Compute/virtualMachineScaleSets':
                nics = list(nmc.network_interfaces.list_virtual_machine_scale_set_network_interfaces(
                            virtual_machine_scale_set_name=resource.name, resource_group_name=group_name))
            else:
                raise('Unexpected resourceType: {}'.format(resource.type))

            for bucket_name in ip_buckets.keys():
                if bucket_name in resource.name:
                    for n in nics:
                        for config in n.ip_configurations:
                            ip_buckets[bucket_name].append(config.private_ip_address)

        print('Detected IP configuration: {}'.format(ip_buckets))

        with tunnel(get_value('linuxAdminUsername'), 'ssh_key', master_lb, port=2200) as t:
            integration_test(
                tunnel=t,
                test_dir='/home/{}'.format(get_value('linuxAdminUsername')),
                dcos_dns=ip_buckets['master'][0],
                master_list=ip_buckets['master'],
                agent_list=ip_buckets['private'],
                public_agent_list=ip_buckets['public'],
                add_env=get_test_config(),
                pytest_cmd=os.getenv('DCOS_PYTEST_CMD', "py.test -vv -s -rs -m 'not ccm' ") + os.getenv('CI_FLAGS', ''))
        test_successful = True
    except Exception as ex:
        traceback.print_exc()
        print("ERROR: exception {}".format(ex))
        raise
    finally:
        if os.getenv('AZURE_CLEANUP') == 'false':
            print("Cluster must be cleaned up manually")
            print("Cluster details: {}".format(azure_cluster))
        else:
            # Send a delete request
            # TODO(cmaloney): The old code had a retry around this:
            # @retry(wait_exponential_multiplier=1000, wait_exponential_max=60*1000, stop_max_delay=(30*60*1000))
            poller = rmc.resource_groups.delete(group_name)

            # poll for the delete to complete
            print("Deleting resource group: {} ...".format(group_name))

            @retry(wait_fixed=(5 * 1000), stop_max_delay=(60 * 60 * 1000))
            def wait_for_delete():
                assert poller.done(), "Timed out waiting for delete"

            print("Waiting for delete ...")
            wait_for_delete()

            print("Clean up successful")

    if test_successful:
        print("Azure test deployment succeeded")
    else:
        print("ERROR: Azure test deployment failed", file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
