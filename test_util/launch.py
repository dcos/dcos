""" Utilities to provide a turn-key deployments of DC/OS clusters, wait
for their deployment to finish, describe the cluster topology, run the
integration tests, and finally delete the cluster.
"""
import abc
import copy
import logging

import ssh.tunnel
import test_util.runner
from pkgpanda.util import load_string
from test_util.aws import BotoWrapper, DcosCfSimple

log = logging.getLogger(__name__)


class LauncherError(Exception):
    def __init__(self, error, msg):
        self.error = error
        self.msg = msg

    def __repr__(self):
        return '{}: {}'.format(self.error, self.msg)


class AbstractLauncher(metaclass=abc.ABCMeta):
    def create(self, config):
        raise NotImplementedError()

    def wait(self, info):
        raise NotImplementedError()

    def describe(self, info):
        raise NotImplementedError()

    def delete(self, info):
        raise NotImplementedError()

    def ssh_from_config(self, info):
        raise NotImplementedError()

    def test(self, info):
        raise NotImplementedError()


class AwsCloudformationLauncher(AbstractLauncher):
    def __init__(self, boto_wrapper):
        self.boto_wrapper = boto_wrapper
        log.debug('Using AWS Cloudformation Launcher')

    def create(self, config):
        check_keys(config, ['stack_name', 'template_url'])
        ssh_info = self.ssh_from_config(config)
        # NOTE: even if parameters not given, ssh_from_config will add KeyName
        # parameter to config['parameters']
        self.boto_wrapper.create_stack(
            config['stack_name'], config['template_url'], config['parameters'])
        return {
            'type': 'cloudformation',
            'stack_name': config['stack_name'],
            'provider': {
                'region': config['provider_info']['region'],
                'access_key_id': config['provider_info']['access_key_id'],
                'secret_access_key': config['provider_info']['secret_access_key']},
            'ssh': ssh_info}

    def wait(self, info):
        # TODO: should this support the case where the cluster is being updated?
        cf = self.get_stack(info)
        status = cf.get_stack_details()['StackStatus']
        if status == 'CREATE_IN_PROGRESS':
            cf.wait_for_stack_creation(wait_before_poll_min=0)
        elif status == 'CREATE_COMPLETE':
            return
        else:
            raise LauncherError('WaitError', 'AWS Stack has entered unexpected state: {}'.format(status))

    def describe(self, info):
        desc = copy.copy(info)
        cf = self.get_stack(info)
        desc.update({
            'masters': convert_host_list(cf.get_master_ips()),
            'private_agents': convert_host_list(cf.get_private_agent_ips()),
            'public_agents': convert_host_list(cf.get_public_agent_ips())})
        return desc

    def delete(self, info):
        if info['ssh']['delete_with_stack']:
            self.boto_wrapper.delete_key_pair(info['ssh']['key_name'])
        self.get_stack(info).delete()

    def ssh_from_config(self, config):
        """
        In AWS simple deploys, SSH is only used for running the integration test suite.
        In order to use SSH with AWS, one must use an SSH key pair that was previously created
        in and downloaded from AWS. The private key cannot be obtained after its creation, so there
        are three supported possibilities:
        1. User has no preset key pair and would like one to be created for just this instance.
            The keypair will be generated and the private key and key name will be added to the
            ssh_info of the cluster info JSON. This key will be marked in the ssh_info for deletion
            by dcos-launch when the entire cluster is deleted. SSH user name cannot be inferred so
            it must still be provided in the ssh_info of the config
        2. User has a preset AWS KeyPair and no corresponding private key. Testing will not be possible
            without the private key, so ssh_info can be completely omitted with no loss.
        3. User has a preset AWS KeyPair and has the corresponding private key. The private key must be
            pointed to with private_key_path in the config ssh_info along with user.

        Case 2 and 3 require specifying key name. The key name can be provided to dcos-launch in two ways:
        1. Passed directly to the template like other template parameters.
        ---
        parameters:
          - ParameterKey: KeyName
            ParameterValue: my_key_name
        ssh_info:
          user: foo
          private_key_path: path_to_my_key
        2. Provided with the other SSH paramters:
        ---
        ssh_info:
          user: foo
          key_name: my_key_name
          private_key_path: path_to_my_key

        This method will take the config dict, determine if a key name is provided, if necessary, generate
        the key and amend the config, and return the ssh_info for the cluster info JSON
        """
        generate_key = False
        key_name = None
        private_key = None
        # Native AWS parameters take precedence
        if 'parameters' in config:
            for p in config['parameters']:
                if p['ParameterKey'] == 'KeyName':
                    key_name = p['ParameterValue']
        # check ssh_info data
        if 'ssh_info' in config:
            if key_name is None:
                key_name = config['ssh_info'].get('key_name', None)
            elif 'key_name' in config['ssh_info']:
                raise LauncherError('ValidationError',
                                    'Provide key name as either a parameter or in ssh_info; not both')
            if 'private_key_path' in config['ssh_info']:
                if key_name is None:
                    raise LauncherError('ValidationError', 'If a private_key_path is provided, '
                                        'then the KeyName template parameter must be set')
                private_key = load_string(config['ssh_info']['private_key_path'])
        if not key_name:
            key_name = config['stack_name']
            generate_key = True
            private_key = self.boto_wrapper.create_key_pair(key_name)
            cf_params = config.get('parameters', list())
            cf_params.append({'ParameterKey': 'KeyName', 'ParameterValue': key_name})
            config['parameters'] = cf_params
        return {
            'delete_with_stack': generate_key,
            'private_key': private_key,
            'key_name': key_name,
            'user': config.get('ssh_info', dict()).get('user', None)}

    def test(self, info, test_cmd):
        ssh_info = info['ssh']
        for param in ['user', 'private_key']:
            if param not in ssh_info:
                raise LauncherError('MissingInfo', 'Cluster was created without providing ssh_info: {}'.format(param))
        details = self.describe(info)
        test_host = details['masters'][0]['public_ip']
        # TODO: section should be generalized for use by other pr
        with ssh.tunnel.tunnel(ssh_info['user'], ssh_info['private_key'], test_host) as test_tunnel:
            return test_util.runner.integration_test(
                tunnel=test_tunnel,
                dcos_dns=test_host,
                master_list=[m['private_ip'] for m in details['masters']],
                agent_list=[a['private_ip'] for a in details['private_agents']],
                public_agent_list=[a['private_ip'] for a in details['public_agents']],
                aws_access_key_id=info['provider']['access_key_id'],
                aws_secret_access_key=info['provider']['secret_access_key'],
                region=info['provider']['region'],
                test_cmd=test_cmd)

    def get_stack(self, info):
        """Returns the correct class interface depending how the AWS CF is configured
        NOTE: only supports Simple Cloudformation currently
        """
        try:
            return DcosCfSimple(info['stack_name'], self.boto_wrapper)
        except Exception as ex:
            raise LauncherError('StackNotFound', '{} is not accessible'.format(info['stack_name'])) from ex


def get_launcher(launcher_type, provider_info):
    """Returns a launcher given a launcher type (string) and a dictionary of
    appropriate provier_info
    """
    if launcher_type == 'cloudformation':
        check_keys(provider_info, ['region', 'access_key_id', 'secret_access_key'])
        boto_wrapper = BotoWrapper(
            provider_info['region'], provider_info['access_key_id'], provider_info['secret_access_key'])
        return AwsCloudformationLauncher(boto_wrapper)
    else:
        raise LauncherError('UnsupportedAction', 'Launcher type not supported: {}'.format(launcher_type))


def convert_host_list(host_list):
    """ Makes Host tuples more readable when using describe
    """
    return [{'private_ip': h.private_ip, 'public_ip': h.public_ip} for h in host_list]


def check_keys(user_dict, key_list):
    missing = [k for k in key_list if k not in user_dict]
    if len(missing) > 0:
        raise LauncherError('MissingInput', 'The following keys were required but '
                            'not provided: {}'.format(repr(missing)))
