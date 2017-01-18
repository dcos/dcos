"""DC/OS Launch

Usage:
  dcos-launch create [--config-path=<path> --info-path=<path>]
  dcos-launch wait [--info-path=<path>]
  dcos-launch describe [--info-path=<path>]
  dcos-launch pytest [--info-path=<path> --env=<envlist>] [--] [<pytest_extras>]...
  dcos-launch delete [--info-path=<path>]

Commands:
  create    Reads the file given by --config-path, creates the cluster described therein
            and finally dumps a JSON file to the path given in --info-path which can then
            be used with the wait, describe, and delete calls.
  wait      Block until the cluster is up and running.
  describe  Return additional information about the composition of the cluster.
  pytest    Runs integration test suite on cluster. Can optionally supply options and arguments to pytest
  delete    Destroying the provided cluster deployment.

Options:
  --config-path=<path>  Path for config to create cluster from [default: config.yaml].
  --info-path=<path>    JSON file output by create and consumed by wait, describe,
                        and delete [default: cluster_info.json].
  --env=<envlist>       Specifies a comma-delimited list of environment variables to be
                        passed from the local environment into the test environment.
"""
import abc
import copy
import os
import sys

from docopt import docopt

import ssh.tunnel
import test_util.runner
from pkgpanda.util import json_prettyprint, load_json, load_string, load_yaml, write_json, YamlParseError
from test_util.aws import BotoWrapper, DcosCfSimple


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


def do_main(args):
    if args['create']:
        info_path = args['--info-path']
        if os.path.exists(info_path):
            raise LauncherError('InputConflict', 'Target info path already exists!')
        config = load_yaml(args['--config-path'])
        check_keys(config, ['type', 'provider_info', 'this_is_a_temporary_config_format_do_not_put_in_production'])
        write_json(info_path, get_launcher(config['type'], config['provider_info']).create(config))
        return 0

    info = load_json(args['--info-path'])
    check_keys(info, ['type', 'provider'])
    launcher = get_launcher(info['type'], info['provider'])

    if args['wait']:
        launcher.wait(info)
        print('Cluster is ready!')
        return 0

    if args['describe']:
        print(json_prettyprint(launcher.describe(info)))
        return 0

    if args['pytest']:
        test_cmd = 'py.test'
        if args['--env'] is not None:
            if '=' in args['--env']:
                # User is attempting to do an assigment with the option
                raise LauncherError('OptionError', "The '--env' option can only pass through environment variables "
                                    "from the current environment. Set variables according to the shell being used.")
            var_list = args['--env'].split(',')
            check_keys(os.environ, var_list)
            test_cmd = ' '.join(['{}={}'.format(e, os.environ[e]) for e in var_list]) + ' ' + test_cmd
        if len(args['<pytest_extras>']) > 0:
            test_cmd += ' ' + ' '.join(args['<pytest_extras>'])
        launcher.test(info, test_cmd)
        return 0

    if args['delete']:
        launcher.delete(info)
        return 0


def main(argv=None):
    args = docopt(__doc__, argv=argv, version='DC/OS Launch v.0.1')

    try:
        return do_main(args)
    except (LauncherError, YamlParseError) as ex:
        print('DC/OS Launch encountered an error!')
        print(repr(ex))
        return 1


if __name__ == '__main__':
    sys.exit(main())
