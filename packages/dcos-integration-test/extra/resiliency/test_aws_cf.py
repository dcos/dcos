import os
from functools import partial

import pytest

import test_util.aws
import test_util.helpers
from test_util.helpers import retry_boto_rate_limits

ENV_FLAG = 'ENABLE_RESILIENCY_TESTING'

pytestmark = pytest.mark.skipif(
    ENV_FLAG not in os.environ or os.environ[ENV_FLAG] != 'true',
    reason='Must explicitly enable resiliency testing with {}'.format(ENV_FLAG))


@pytest.fixture(scope='session')
def dcos_launchpad(dcos_api_session):
    """Interface for direct integration to dcos_launchpad hardware
    Currently only supports AWS CF with AWS VPC coming soon
    """
    if 'AWS_STACK_NAME' not in os.environ:
        # TODO(mellenburg): update when advanced templates are merged
        pytest.skip('Must use a AWS Cloudformation to run test')
    stack_name = os.environ['AWS_STACK_NAME']
    aws_region = os.environ['AWS_REGION']
    aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID']
    aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']
    bw = test_util.aws.BotoWrapper(aws_region, aws_access_key_id, aws_secret_access_key)
    return test_util.aws.DcosCfSimple(stack_name, bw)


@pytest.mark.last
def test_agent_failure(dcos_launchpad, dcos_api_session, vip_apps):
    # make sure the app works before starting
    @retry_boto_rate_limits
    def get_running_agents(group_name):
        return [i for i in dcos_launchpad.get_auto_scaling_instances(group_name)
                if i.state['Name'] == 'running']

    test_util.helpers.wait_for_pong(vip_apps[0][1], 120)
    test_util.helpers.wait_for_pong(vip_apps[1][1], 10)
    agents = [i.instance_id for i in get_running_agents('PublicSlaveServerGroup') +
              get_running_agents('SlaveServerGroup')]

    # Agents are in auto-scaling groups, so they will automatically be replaced
    dcos_launchpad.boto_wrapper.client('ec2').terminate_instances(InstanceIds=agents)
    waiter = dcos_launchpad.boto_wrapper.client('ec2').get_waiter('instance_terminated')
    retry_boto_rate_limits(waiter.wait)(InstanceIds=agents)

    # Tell mesos the machines are "down" and not coming up so things get rescheduled.
    down_hosts = [{'hostname': slave, 'ip': slave} for slave in dcos_api_session.all_slaves]
    dcos_api_session.post(
        '/mesos/maintenance/schedule',
        json={'windows': [{
            'machine_ids': down_hosts,
            'unavailability': {'start': {'nanoseconds': 0}}
        }]}).raise_for_status()
    dcos_api_session.post('/mesos/machine/down', json=down_hosts).raise_for_status()

    # Wait for replacements
    test_util.helpers.wait_for_len(partial(get_running_agents, 'SlaveServerGroup'), len(dcos_api_session.slaves), 600)
    test_util.helpers.wait_for_len(
        partial(get_running_agents, 'PublicSlaveServerGroup'), len(dcos_api_session.public_slaves), 600)

    # Reset the dcos_api_session to have the replacement agents
    dcos_api_session.slaves = sorted([agent.private_ip_address for agent in
                                      get_running_agents('SlaveServerGroup')])
    dcos_api_session.public_slaves = sorted([agent.private_ip_address for agent in
                                             get_running_agents('PublicSlaveServerGroup')])
    dcos_api_session.all_slaves = sorted(dcos_api_session.slaves + dcos_api_session.public_slaves)

    # verify that everything else is still working
    dcos_api_session.wait_for_dcos()
    # finally verify that the app is again running somewhere with its VIPs
    # Give marathon five minutes to deploy both the apps
    test_util.helpers.wait_for_pong(vip_apps[0][1], 300)
    test_util.helpers.wait_for_pong(vip_apps[1][1], 10)
