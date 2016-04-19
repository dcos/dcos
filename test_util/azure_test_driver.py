#!/usr/bin/env python3

import json
import os
import re
import sys
import traceback

import requests
from retrying import retry

from gen.azure.azure_client import (AzureClient, AzureClientException,
                                    AzureClientTemplateException,
                                    TemplateProvisioningState)


def verify_template_syntax(client, template_body_json, template_parameters):
    print("Verifying template ...")
    try:
        client.verify(template_body_json=template_body_json,
                      template_parameters=template_parameters)
    except AzureClientTemplateException as e:
        print("Template verification failed\n{}".format(e), file=sys.stderr)
        sys.exit(1)
    print("Template OK!")


def json_pretty_print(json_str, file=sys.stdout):
    print(json.dumps(json_str, sort_keys=True, indent=4, separators=(',', ':')), file=file)


def get_template_output(client):
    '''
    Returns the ARM deployment output values which has the format:
      {
        'output_key': {
          'value': 'output_value',
          'type': 'String'
        }
      }
    '''
    r = client.get_template_deployment()
    return r.get('properties', {}).get('outputs', {})


def get_template_output_value(client, *output_keys):
    '''
    Given a tuple of output_keys, return the value for the first matching key
    in the template output.  This is useful for testing templates which have
    different keys for the same output value. Raises an AzureClientException if
    none of the keys are found.
    '''
    outputs = get_template_output(client)
    for k in output_keys:
        if k in outputs:
            return outputs.get(k).get('value')
    raise AzureClientException("Unable to find any of the output_keys {} in deployment".format(output_keys))


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
    env_param_regex = re.compile(r"AZURE_PARAM_(?P<param>.*)")
    env_param_int_regex = re.compile(r"AZURE_PARAM_INT_(?P<param>.*)")
    for env_key, env_val in os.environ.items():
        match_string = env_param_regex.match(env_key)
        match_int = env_param_int_regex.match(env_key)
        if match_int:
            print("Env parameter (String): {}={}".format(match_int.group('param'), env_val))
            template_params[match_int.group('param')] = {"value": int(env_val)}
        elif match_string:
            print("Env parameter (Integer): {}={}".format(match_string.group('param'), env_val))
            template_params[match_string.group('param')] = {"value": env_val}

    return(template_params)


def run():
    template_path = os.environ['AZURE_TEMPLATE_PATH']
    arm = open(template_path).read()

    location = os.getenv('AZURE_LOCATION', 'East US')

    template_params = get_env_params()

    client = AzureClient.create_from_env_creds(
        random_resource_group_name_prefix='teamcity')

    # Output resource group
    print("Resource group name: {}".format(client._resource_group_name))
    print("Deployment name: {}".format(client._deployment_name))

    azure_cluster = {
                        'resource_group_name': client._resource_group_name,
                        'deployment_name': client._deployment_name
                    }

    open('azure-cluster.json', mode='w').write(json.dumps(azure_cluster))

    # Create a new resource group
    print("Creating new resource group in location: {}".format(location))
    print(client.create_resource_group(location))

    test_successful = False

    try:
        # Use RPC against azure to validate the ARM template is well-formed
        verify_template_syntax(client,
                               template_body_json=json.loads(arm),
                               template_parameters=template_params)

        # Actually create a template deployment
        print("Creating template deployment ...")
        deployment_response = client.create_template_deployment(
            template_body_json=json.loads(arm),
            template_parameters=template_params)
        json_pretty_print(deployment_response)

        # For deploying templates, stop_max_delay must be long enough to handle the ACS template which does not signal
        # success until leader.mesos is resolvable.
        @retry(wait_fixed=(5*1000),
               stop_max_delay=(45*60*1000),
               retry_on_exception=lambda x: isinstance(x, AssertionError))
        def poll_on_template_deploy_status(client):
            provisioning_state = client.get_template_deployment()['properties']['provisioningState']
            if provisioning_state == TemplateProvisioningState.FAILED:
                failed_ops = client.list_template_deployment_operations(provisioning_state)
                raise AzureClientException("Template failed to deploy: {}".format(failed_ops))
            assert provisioning_state == TemplateProvisioningState.SUCCEEDED, \
                "Template did not finish deploying in time, provisioning state: {}".format(provisioning_state)

        print("Waiting for template to deploy ...")
        poll_on_template_deploy_status(client)
        print("Template deployed successfully")

        master_lb = get_template_output_value(client, 'dnsAddress', 'masterFQDN')
        master_url = "http://{}".format(master_lb)

        print("Template deployed using SSH private key: https://mesosphere.onelogin.com/notes/18444")
        print("For troubleshooting, master0 can be reached using: ssh -p 2200 core@{}".format(master_lb))

        @retry(wait_fixed=(5*1000), stop_max_delay=(15*60*1000))
        def poll_on_dcos_ui_up(master_url):
            r = get_dcos_ui(master_url)
            assert r is not None and r.status_code == requests.codes.ok, \
                "Unable to reach DC/OS UI: {}".format(master_url)

        print("Waiting for DC/OS UI at: {} ...".format(master_url))
        poll_on_dcos_ui_up(master_url)
        test_successful = True

    except (AssertionError, AzureClientException) as ex:
        print("ERROR: {}".format(ex), file=sys.stderr)
        traceback.print_tb(ex.__traceback__)

    finally:
        @retry(wait_exponential_multiplier=1000, wait_exponential_max=60*1000, stop_max_delay=(30*60*1000))
        def delete_resource_group(client):
            del_response = client.delete_resource_group()
            assert del_response.status_code == requests.codes.accepted, \
                "Delete request failed: {}".format(del_response.status_code)
            return del_response.headers['Location']

        print("Deleting resource group: {} ...".format(client._resource_group_name))
        poll_location = delete_resource_group(client)

        @retry(wait_fixed=(5*1000), stop_max_delay=(60*60*1000))
        def wait_for_delete(poll_location):
            r = client.status_delete_resource_group(poll_location)
            assert r.status_code == requests.codes.ok, "Timed out waiting for delete: {}".format(r.status_code)

        print("Waiting for delete ...")
        wait_for_delete(poll_location)

        print("Clean up successful")

    if test_successful:
        print("Azure test deployment succeeded")
    else:
        print("ERROR: Azure test deployment failed", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    run()
