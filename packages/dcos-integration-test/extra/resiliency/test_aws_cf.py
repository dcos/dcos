import logging
import os
import subprocess

import pytest
import requests
import retrying
import test_util.aws


@pytest.fixture(scope='session')
def provider(cluster):
    """Interface for direct interation to provider hardware
    Currently only supports AWS CF with AWS VPC coming soon
    """
    if cluster.provider != 'aws':
        pytest.skip('Must be AWS CF to run test')
    aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID']
    aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']
    aws_region = os.environ['AWS_REGION']
    stack_name = os.environ['AWS_STACK_NAME']
    bw = test_util.aws.BotoWrapper(aws_region, aws_access_key_id, aws_secret_access_key)
    return test_util.aws.DcosCfSimple(stack_name, bw)


@retrying.retry(wait_fixed=3000, stop_max_delay=300 * 1000)
def wait_for_persistent_app(url):
    logging.info('Attempting to ping test application')
    r = requests.get('http://{}/ping'.format(url))
    assert r.ok, 'Bad response from test server: ' + str(r.status_code)
    assert r.json() == {"pong": True}, 'Unexpected response from server: ' + repr(r.json())


@retrying.retry(wait_fixed=3000, stop_max_delay=600 * 1000,
                retry_on_result=lambda res: res is False,
                retry_on_exception=lambda ex: False)
def wait_for_group_population(provider, group, target):
    count = len(provider.get_group_instances(group))
    logging.info('Waiting for {} to have {} agents. Current count: {}'.format(group, target, count))
    if count < target:
        return False


@pytest.mark.resiliency
def test_agent_failure(provider, cluster, vip_apps):
    # make sure the app works before starting
    wait_for_persistent_app(vip_apps[0][1])
    wait_for_persistent_app(vip_apps[1][1])

    agents = [i['InstanceId'] for i in provider.
              get_group_instances(['PublicSlaveServerGroup', 'SlaveServerGroup'])]
    # First, need to make sure the cluster will recover to the same state
    num_public = len(cluster.public_slaves)
    num_private = len(cluster.slaves)
    provider.set_autoscaling_group_capacity('PublicSlaveServerGroup', num_public)
    provider.set_autoscaling_group_capacity('SlaveServerGroup', num_private)

    # Agents are in autoscaling groups, so they will automatically be replaced
    provider.boto_wrapper.client('ec2').terminate_instances(InstanceIds=agents)
    provider.boto_wrapper.client('ec2').get_waiter('instance_terminated').wait(InstanceIds=agents)

    # Wait for replacements
    wait_for_group_population(provider, ['PublicSlaveServerGroup'], num_public)
    wait_for_group_population(provider, ['SlaveServerGroup'], num_private)

    # Reset the cluster to have the replacement agents
    cluster.slaves = sorted([agent.private_ip for agent in
                             provider.get_private_agent_ips(state_list=['running'])])
    cluster.public_slaves = sorted([agent.private_ip for agent in
                                    provider.get_public_agent_ips(state_list=['running'])])
    cluster.all_slaves = sorted(cluster.slaves + cluster.public_slaves)

    # verify that everything else is still working
    cluster._wait_for_dcos()
    # finally verify that the app is again running somewhere with its VIPs
    wait_for_persistent_app(vip_apps[0][1])
    wait_for_persistent_app(vip_apps[1][1])


@pytest.yield_fixture
def masters_down(provider, cluster):
    if len(cluster.masters) == 1:
        # only works for multi master scenarios
        pytest.skip()
    this_master = subprocess.check_output(['/opt/mesosphere/bin/detect-ip'])
    masters_down = []
    for master in cluster.masters:
        if master != this_master:
            instance = provider.get_instance_from_ip(master)
            instance.stop()
            masters_down.append(instance)
    yield
    for master in masters_down:
        master.start()


def dtest_highly_available_apis(masters_down, cluster):
    pass
