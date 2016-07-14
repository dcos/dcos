#!/usr/bin/env python3
import os
import random
import sys
import uuid
from contextlib import closing

import azure.common.credentials
import requests
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource.resources import ResourceManagementClient
from azure.mgmt.resource.resources.models import (DeploymentMode,
                                                  DeploymentProperties,
                                                  ResourceGroup, TemplateLink)
from retrying import retry

import pkgpanda.util
from ssh.ssh_tunnel import SSHTunnel
from test_util.test_runner import integration_test


def get_dcos_ui(master_url):
    try:
        return requests.get(master_url)
    except requests.exceptions.ConnectionError:
        pass


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


def run():
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
    group_name = 'tesing' + ''.join(random.choice('01234567890abcdef') for n in range(10))
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
        template_parameters['numberOfPrivateSlaves'] = {'value': 2}
        template_parameters['numberOfPublicSlaves'] = {'value': 1}
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
        master_lb = deployment_result.properties.outputs['dnsAddress']['value']
        master_url = "http://{}".format(master_lb)

        print("Template deployed using SSH private key: https://mesosphere.onelogin.com/notes/18444")
        print("For troubleshooting, master0 can be reached using: ssh -p 2200 core@{}".format(master_lb))

        @retry(wait_fixed=(5 * 1000), stop_max_delay=(15 * 60 * 1000))
        def poll_on_dcos_ui_up():
            r = get_dcos_ui(master_url)
            assert r is not None and r.status_code == requests.codes.ok, \
                "Unable to reach DC/OS UI: {}".format(master_url)

        print("Waiting for DC/OS UI at: {} ...".format(master_url))
        poll_on_dcos_ui_up()

        # Run test now, so grab IPs
        nmc = NetworkManagementClient(credentials, subscription_id)
        ip_buckets = {
            'masterNodeNic': [],
            'slavePrivateNic': [],
            'slavePublicNic': []}

        for resource in rmc.resource_groups.list_resources(group_name):
            for bucket_name, bucket in ip_buckets.items():
                if resource.name.startswith(bucket_name):
                    nic = nmc.network_interfaces.get(group_name, resource.name)
                    all_ips = []
                    for config in nic.ip_configurations:
                        all_ips.append(config.private_ip_address)
                    bucket.extend(all_ips)

        with closing(SSHTunnel('core', 'ssh_key', master_lb, port=2200)) as t:
            integration_test(
                    tunnel=t,
                    test_dir='/home/core',
                    dcos_dns=master_lb,
                    master_list=ip_buckets['masterNodeNic'],
                    agent_list=ip_buckets['slavePrivateNic'],
                    public_agent_list=ip_buckets['slavePublicNic'],
                    provider='azure',
                    test_dns_search=True,
                    ci_flags=os.getenv('CI_FLAGS', ''))
        test_successful = True
    except Exception as ex:
        print("ERROR: exception {}".format(ex))
        raise
    finally:
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
    run()
