import os

import pytest

import test_util.aws
import test_util.helpers


@pytest.fixture(scope='session')
def dcos_launchpad(cluster):
    """Interface for direct interation to dcos_launchpad hardware
    Currently only supports AWS CF with AWS VPC coming soon
    """
    if cluster.provider != 'aws':
        # TODO(mellenburg): update when advanced templates are merged
        pytest.skip('Must be AWS CF to run test')
    aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID']
    aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']
    aws_region = os.environ['AWS_REGION']
    stack_name = os.environ['AWS_STACK_NAME']
    bw = test_util.aws.BotoWrapper(aws_region, aws_access_key_id, aws_secret_access_key)
    return test_util.aws.DcosCfSimple(stack_name, bw)


@pytest.mark.last
@pytest.mark.resiliency
def test_agent_failure(dcos_launchpad, cluster, vip_apps):
    # make sure the app works before starting
    test_util.helpers.wait_for_pong(vip_apps[0][1], 120)
    test_util.helpers.wait_for_pong(vip_apps[1][1], 10)

    agents = [i['InstanceId'] for i in dcos_launchpad.
              get_group_instances(['PublicSlaveServerGroup', 'SlaveServerGroup'], state_list=['running'])]

    # Agents are in autoscaling groups, so they will automatically be replaced
    dcos_launchpad.boto_wrapper.client('ec2').terminate_instances(InstanceIds=agents)
    dcos_launchpad.boto_wrapper.client('ec2').get_waiter('instance_terminated').wait(InstanceIds=agents)

    def get_running_agents():
        return dcos_launchpad.get_group_instances(
            ['PublicSlaveServerGroup', 'SlaveServerGroup'], state_list=['running'])

    # Tell mesos the machines are "down" and not coming up so things get rescheduled.
    down_hosts = [{'hostname': slave, 'ip': slave} for slave in cluster.all_slaves]
    cluster.post(
        '/mesos/maintenance/schedule',
        json={'windows': [{
            'machine_ids': down_hosts,
            'unavailability': {'start': {'nanoseconds': 0}}
        }]}).raise_for_status()
    cluster.post('/mesos/machine/down', json=down_hosts).raise_for_status()

    # Wait for replacements
    test_util.helpers.wait_for_len(get_running_agents, len(cluster.all_slaves), 600)

    # Reset the cluster to have the replacement agents
    cluster.slaves = sorted([agent.private_ip for agent in
                             dcos_launchpad.get_private_agent_ips(state_list=['running'])])
    cluster.public_slaves = sorted([agent.private_ip for agent in
                                    dcos_launchpad.get_public_agent_ips(state_list=['running'])])
    cluster.all_slaves = sorted(cluster.slaves + cluster.public_slaves)

    # verify that everything else is still working
    cluster.wait_for_dcos()
    # finally verify that the app is again running somewhere with its VIPs
    # Give marathon five minutes to deploy both the apps
    test_util.helpers.wait_for_pong(vip_apps[0][1], 300)
    test_util.helpers.wait_for_pong(vip_apps[1][1], 10)
