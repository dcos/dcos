from contextlib import contextmanager

import pytest

import launch
import ssh
import test_util
from launch.util import get_temp_config_path, stub
from test_util.helpers import Host


@contextmanager
def mocked_context(*args, **kwargs):
    """ To be directly patched into an ssh.tunnel invocation to prevent
    any real SSH attempt
    """
    yield type('Tunnelled', (object,), {})


@pytest.fixture
def mocked_test_runner(monkeypatch):
    monkeypatch.setattr(ssh.tunnel, 'tunnel', mocked_context)
    monkeypatch.setattr(test_util.runner, 'integration_test', stub(0))


@pytest.fixture
def ssh_key_path(tmpdir):
    ssh_key_path = tmpdir.join('ssh_key')
    ssh_key_path.write(launch.util.MOCK_SSH_KEY_DATA)
    return str(ssh_key_path)


class MockStack:
    def __init__(self):
        self.stack_id = launch.util.MOCK_STACK_ID


@pytest.fixture
def mocked_aws_cf(monkeypatch, mocked_test_runner):
    """Does not include SSH key mocking
    """
    monkeypatch.setattr(test_util.aws.DcosCfStack, '__init__', stub(None))
    monkeypatch.setattr(
        test_util.aws, 'fetch_stack', lambda stack_name, bw: test_util.aws.DcosCfStack(stack_name, bw))
    # mock create
    monkeypatch.setattr(test_util.aws.BotoWrapper, 'create_stack', stub(MockStack()))
    # mock wait
    monkeypatch.setattr(test_util.aws.CfStack, 'wait_for_complete', stub(None))
    # mock describe
    monkeypatch.setattr(test_util.aws.DcosCfStack, 'get_master_ips',
                        stub([Host('127.0.0.1', '12.34.56')]))
    monkeypatch.setattr(test_util.aws.DcosCfStack, 'get_private_agent_ips',
                        stub([Host('127.0.0.1', None)]))
    monkeypatch.setattr(test_util.aws.DcosCfStack, 'get_public_agent_ips',
                        stub([Host('127.0.0.1', '12.34.56')]))
    # mock delete
    monkeypatch.setattr(test_util.aws.DcosCfStack, 'delete', stub(None))
    monkeypatch.setattr(test_util.aws.BotoWrapper, 'delete_key_pair', stub(None))
    # mock config
    monkeypatch.setattr(test_util.aws.BotoWrapper, 'create_key_pair', stub(launch.util.MOCK_SSH_KEY_DATA))


@pytest.fixture
def mocked_aws_zen_cf(monkeypatch, mocked_aws_cf):
    monkeypatch.setattr(test_util.aws.DcosZenCfStack, '__init__', stub(None))
    monkeypatch.setattr(
        test_util.aws, 'fetch_stack', lambda stack_name, bw: test_util.aws.DcosZenCfStack(stack_name, bw))
    # mock create
    monkeypatch.setattr(test_util.aws.BotoWrapper, 'create_vpc_tagged', stub(launch.util.MOCK_VPC_ID))
    monkeypatch.setattr(test_util.aws.BotoWrapper, 'create_internet_gateway_tagged', stub(launch.util.MOCK_GATEWAY_ID))
    monkeypatch.setattr(test_util.aws.BotoWrapper, 'create_subnet_tagged', stub(launch.util.MOCK_SUBNET_ID))
    # mock delete
    monkeypatch.setattr(test_util.aws.BotoWrapper, 'delete_subnet', stub(None))
    monkeypatch.setattr(test_util.aws.BotoWrapper, 'delete_vpc', stub(None))
    monkeypatch.setattr(test_util.aws.BotoWrapper, 'delete_internet_gateway', stub(None))
    # mock describe
    monkeypatch.setattr(test_util.aws.DcosZenCfStack, 'get_master_ips',
                        stub([Host('127.0.0.1', '12.34.56')]))
    monkeypatch.setattr(test_util.aws.DcosZenCfStack, 'get_private_agent_ips',
                        stub([Host('127.0.0.1', None)]))
    monkeypatch.setattr(test_util.aws.DcosZenCfStack, 'get_public_agent_ips',
                        stub([Host('127.0.0.1', '12.34.56')]))
    # mock delete
    monkeypatch.setattr(test_util.aws.DcosZenCfStack, 'delete', stub(None))


@pytest.fixture
def aws_cf_config_path(tmpdir, ssh_key_path, mocked_aws_cf):
    return get_temp_config_path(tmpdir, 'aws-cf.yaml', update={'ssh_private_key_filename': ssh_key_path})


@pytest.fixture
def aws_cf_with_helper_config_path(tmpdir, mocked_aws_cf):
    return get_temp_config_path(tmpdir, 'aws-cf-with-helper.yaml')


@pytest.fixture
def aws_zen_cf_config_path(tmpdir, ssh_key_path, mocked_aws_zen_cf):
    return get_temp_config_path(tmpdir, 'aws-zen-cf.yaml')


@pytest.fixture
def aws_cf_no_pytest_config_path(tmpdir, mocked_aws_cf):
    return get_temp_config_path(tmpdir, 'aws-cf-no-pytest.yaml')


@pytest.fixture
def azure_config_path(tmpdir):
    return get_temp_config_path(tmpdir, 'azure.yaml')


@pytest.fixture
def azure_with_helper_config_path(tmpdir):
    return get_temp_config_path(tmpdir, 'azure-with-helper.yaml')


@pytest.fixture
def aws_onprem_config_path(tmpdir, ssh_key_path):
    return get_temp_config_path(tmpdir, 'aws-onprem.yaml', update={'ssh_private_key_filename': ssh_key_path})


@pytest.fixture
def aws_onprem_with_helper_config_path(tmpdir):
    return get_temp_config_path(tmpdir, 'aws-onprem-with-helper.yaml')


@pytest.fixture
def aws_bare_cluster_config_path(tmpdir, ssh_key_path):
    return get_temp_config_path(tmpdir, 'aws-bare-cluster.yaml', update={'ssh_private_key_filename': ssh_key_path})


@pytest.fixture
def bare_cluster_onprem_config_path(tmpdir, ssh_key_path):
    platform_info_path = tmpdir.join('bare_cluster_info.json')
    platform_info_path.write("""
{
    "ssh_user": "core"
}
""")
    return get_temp_config_path(tmpdir, 'bare-cluster-onprem.yaml', update={
        'ssh_private_key_filename': ssh_key_path,
        'platform_info_filename': str(platform_info_path)})
