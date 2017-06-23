import logging
import os

import pytest
import retrying

import test_util.aws
import test_util.helpers
from test_util.helpers import retry_boto_rate_limits

log = logging.getLogger(__name__)

ENV_FLAG = 'ENABLE_RESILIENCY_TESTING'

skip_if_resiliency_not_enabled = pytest.mark.skipif(
    ENV_FLAG not in os.environ or os.environ[ENV_FLAG] != 'true',
    reason='Must explicitly enable resiliency testing with {}'.format(ENV_FLAG))

skip_if_not_aws_stack = pytest.mark.skipif(
    'AWS_STACK_NAME' not in os.environ,
    reason='Must use an AWS Cloudformation run this test!')

pytestmark = [skip_if_resiliency_not_enabled, skip_if_not_aws_stack]


@pytest.fixture(scope='session')
def boto_wrapper(dcos_api_session):
    aws_region = os.environ['AWS_REGION']
    aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID']
    aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']
    return test_util.aws.BotoWrapper(aws_region, aws_access_key_id, aws_secret_access_key)


@pytest.fixture(scope='session')
def dcos_stack(boto_wrapper):
    """ Works with either Zen or Simple cloud formations
    """
    stack = test_util.aws.fetch_stack(os.environ['AWS_STACK_NAME'], boto_wrapper)
    if isinstance(stack, test_util.aws.BareClusterCfStack):
        pytest.skip('Onprem Vpc not currently supported')
    return stack


@pytest.mark.last
def test_agent_failure(dcos_stack, boto_wrapper, dcos_api_session, vip_apps):
    # Accessing AWS Resource objects will trigger a client describe call.
    # As such, any method that touches AWS APIs must be wrapped to avoid
    # CI collapse when rate limits are inevitably reached
    @retry_boto_rate_limits
    def get_running_instances(instance_iter):
        return [i for i in instance_iter if i.state['Name'] == 'running']

    @retry_boto_rate_limits
    def get_instance_ids(instance_iter):
        return [i.instance_id for i in instance_iter]

    @retry_boto_rate_limits
    def get_private_ips(instance_iter):
        return sorted([i.private_ip_address for i in get_running_instances(instance_iter)])

    # make sure the app works before starting
    test_util.helpers.wait_for_pong(vip_apps[0][1], 120)
    test_util.helpers.wait_for_pong(vip_apps[1][1], 10)
    agent_ids = get_instance_ids(
        get_running_instances(dcos_stack.public_agent_instances) +
        get_running_instances(dcos_stack.private_agent_instances))

    # Agents are in auto-scaling groups, so they will automatically be replaced
    boto_wrapper.client('ec2').terminate_instances(InstanceIds=agent_ids)
    waiter = boto_wrapper.client('ec2').get_waiter('instance_terminated')
    retry_boto_rate_limits(waiter.wait)(InstanceIds=agent_ids)

    # Tell mesos the machines are "down" and not coming up so things get rescheduled.
    down_hosts = [{'hostname': slave, 'ip': slave} for slave in dcos_api_session.all_slaves]
    dcos_api_session.post(
        '/mesos/maintenance/schedule',
        json={'windows': [{
            'machine_ids': down_hosts,
            'unavailability': {'start': {'nanoseconds': 0}}
        }]}).raise_for_status()
    dcos_api_session.post('/mesos/machine/down', json=down_hosts).raise_for_status()

    public_agent_count = len(dcos_api_session.public_slaves)
    private_agent_count = len(dcos_api_session.slaves)

    @retrying.retry(
        wait_fixed=60 * 1000,
        retry_on_result=lambda res: res is False,
        stop_max_delay=900 * 1000)
    def wait_for_agents_to_refresh():
        public_agents = get_running_instances(dcos_stack.public_agent_instances)
        if len(public_agents) == public_agent_count:
            dcos_api_session.public_slave_list = get_private_ips(public_agents)
        else:
            log.info('Waiting for {} public agents. Current: {}'.format(
                     public_agent_count, len(public_agents)))
            return False
        private_agents = get_running_instances(dcos_stack.private_agent_instances)
        if len(private_agents) == private_agent_count:
            dcos_api_session.slave_list = get_private_ips(private_agents)
        else:
            log.info('Waiting for {} private agents. Current: {}'.format(
                     private_agent_count, len(private_agents)))
            return False

    wait_for_agents_to_refresh()

    # verify that everything else is still working
    dcos_api_session.wait_for_dcos()
    # finally verify that the app is again running somewhere with its VIPs
    # Give marathon five minutes to deploy both the apps
    test_util.helpers.wait_for_pong(vip_apps[0][1], 300)
    test_util.helpers.wait_for_pong(vip_apps[1][1], 10)
