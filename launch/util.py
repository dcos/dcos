import abc
import logging

import pkg_resources
import yaml

import pkgpanda
import ssh.tunnel
import test_util.runner

log = logging.getLogger(__name__)

MOCK_SSH_KEY_DATA = 'ssh_key_data'
MOCK_KEY_NAME = 'my_key_name'
MOCK_VPC_ID = 'vpc-foo-bar'
MOCK_SUBNET_ID = 'subnet-foo-bar'
MOCK_GATEWAY_ID = 'gateway-foo-bar'
MOCK_STACK_ID = 'this-is-a-important-test-stack::deadbeefdeadbeef'


def stub(output):
    def accept_any_args(*args, **kwargs):
        return output
    return accept_any_args


def get_temp_config_path(tmpdir, name, update: dict = None):
    config = pkgpanda.util.load_yaml(
        pkg_resources.resource_filename('launch', 'sample_configs/{}'.format(name)))
    if update is not None:
        config.update(update)
    new_config_path = tmpdir.join('my_config.yaml')
    new_config_path.write(yaml.dump(config))
    # sample configs specifically use ip-detect.sh for easy mocking
    tmpdir.join('ip-detect.sh').write(pkg_resources.resource_string('gen', 'ip-detect/aws.sh').decode())
    return str(new_config_path)


def check_keys(user_dict, key_list):
    missing = [k for k in key_list if k not in user_dict]
    if len(missing) > 0:
        raise LauncherError('MissingInput', 'The following keys were required but '
                            'not provided: {}'.format(repr(missing)))


class LauncherError(Exception):
    def __init__(self, error, msg):
        self.error = error
        self.msg = msg

    def __repr__(self):
        return '{}: {}'.format(self.error, self.msg if self.msg else self.__cause__)


class AbstractLauncher(metaclass=abc.ABCMeta):
    def create(self, config):
        raise NotImplementedError()

    def wait(self, info):
        raise NotImplementedError()

    def describe(self, info):
        raise NotImplementedError()

    def delete(self, info):
        raise NotImplementedError()

    def test(self, info, test_cmd):
        try:
            check_keys(info, ['ssh_user', 'ssh_private_key'])
        except LauncherError:
            print('DC/OS Launch is missing sufficient SSH info to run tests!')
            raise
        details = self.describe(info)
        test_host = details['masters'][0]['public_ip']
        with ssh.tunnel.tunnel(info['ssh_user'], info['ssh_private_key'], test_host) as test_tunnel:
            return test_util.runner.integration_test(
                tunnel=test_tunnel,
                dcos_dns=test_host,
                master_list=[m['private_ip'] for m in details['masters']],
                agent_list=[a['private_ip'] for a in details['private_agents']],
                public_agent_list=[a['private_ip'] for a in details['public_agents']],
                aws_access_key_id=info['aws_access_key_id'],
                aws_secret_access_key=info['aws_secret_access_key'],
                region=info['aws_region'],
                test_cmd=test_cmd)


def convert_host_list(host_list):
    """ Makes Host tuples more readable when using describe
    """
    return [{'private_ip': h.private_ip, 'public_ip': h.public_ip} for h in host_list]
