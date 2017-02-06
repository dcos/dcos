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
from test_util.aws import BotoWrapper, fetch_stack


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

    def ssh_from_config(self, info):
        raise NotImplementedError()

    def test(self, info, test_cmd):
        ssh_info = info['ssh']
        try:
            check_keys(ssh_info, ['user', 'private_key'])
        except LauncherError:
            print('DC/OS Launch is missing sufficient SSH info to run tests!')
            raise
        details = self.describe(info)
        test_host = details['masters'][0]['public_ip']
        with ssh.tunnel.tunnel(ssh_info['user'], ssh_info['private_key'], test_host) as test_tunnel:
            return test_util.runner.integration_test(
                tunnel=test_tunnel,
                dcos_dns=test_host,
                master_list=[m['private_ip'] for m in details['masters']],
                agent_list=[a['private_ip'] for a in details['private_agents']],
                public_agent_list=[a['private_ip'] for a in details['public_agents']],
                aws_access_key_id=info['provider'].get('access_key_id'),
                aws_secret_access_key=info['provider'].get('secret_access_key'),
                region=info['provider'].get('region'),
                test_cmd=test_cmd)


class AwsCloudformationLauncher(AbstractLauncher):
    def __init__(self, boto_wrapper):
        self.boto_wrapper = boto_wrapper

    def create(self, config):
        """
        Checks config and creates missing resources as necessary
        If actual stack creation fails, then network resources
        will be cleaned up

        Note: ssh_from_config and provide_network_prereqs will mutate
            config
        """
        check_keys(config, ['stack_name', 'template_url'])
        ssh_info, temp_resources = self.ssh_from_config(config)
        if config.get('zen_helper', False):
            temp_resources.update(self.provide_network_prereqs(config))
        try:
            stack = self.boto_wrapper.create_stack(
                config['stack_name'], config['template_url'], config['parameters'])
        except Exception as ex:
            self.delete_temp_resources(temp_resources)
            raise LauncherError('ProviderError', None) from ex
        return {
            'type': 'cloudformation',
            'stack_id': stack.stack_id,
            'provider': {
                'region': config['provider_info']['region'],
                'access_key_id': config['provider_info']['access_key_id'],
                'secret_access_key': config['provider_info']['secret_access_key']},
            'ssh': ssh_info,
            'temp_resources': temp_resources}

    def provide_network_prereqs(self, config):
        """ Loops through parameters given to AWS CF templates to determine if
        the keywords for Zen template prerequisites are met. If not met, they
        will be provided (must be done in correct order) and added to the info
        JSON as 'temp_resources'

        TODO: change config format to provide key-value parameters as a simple
          dict-like object rather than this boilerplate list
        """
        parameters = config.get('parameters', list())
        vpc_found = False
        gateway_found = False
        private_subnet_found = False
        public_subnet_found = False
        for param in parameters:
            key = param['ParameterKey']
            if key == 'Vpc':
                vpc_found = True
                vpc_id = param['ParameterValue']
            elif key == 'InternetGateway':
                gateway_found = True
            elif key == 'PrivateSubnet':
                private_subnet_found = True
            elif key == 'PublicSubnet':
                public_subnet_found = True
        temp_resources = {}

        if not vpc_found:
            vpc_id = self.boto_wrapper.create_vpc_tagged('10.0.0.0/16', config['stack_name'])
            parameters.append({'ParameterKey': 'Vpc', 'ParameterValue': vpc_id})
            temp_resources.update({'vpc': vpc_id})
        if not gateway_found:
            gateway_id = self.boto_wrapper.create_internet_gateway_tagged(vpc_id, config['stack_name'])
            parameters.append({'ParameterKey': 'InternetGateway', 'ParameterValue': gateway_id})
            temp_resources.update({'gateway': gateway_id})
        if not private_subnet_found:
            private_subnet_id = self.boto_wrapper.create_subnet_tagged(
                vpc_id, '10.0.0.0/17', config['stack_name'] + 'private')
            parameters.append({'ParameterKey': 'PrivateSubnet', 'ParameterValue': private_subnet_id})
            temp_resources.update({'private_subnet': private_subnet_id})
        if not public_subnet_found:
            public_subnet_id = self.boto_wrapper.create_subnet_tagged(
                vpc_id, '10.0.128.0/20', config['stack_name'] + '-public')
            parameters.append({'ParameterKey': 'PublicSubnet', 'ParameterValue': public_subnet_id})
            temp_resources.update({'public_subnet': public_subnet_id})
        config['parameters'] = parameters
        return temp_resources

    def wait(self, info):
        self.get_stack(info).wait_for_complete()

    def describe(self, info):
        desc = copy.copy(info)
        cf = self.get_stack(info)
        desc.update({
            'masters': convert_host_list(cf.get_master_ips()),
            'private_agents': convert_host_list(cf.get_private_agent_ips()),
            'public_agents': convert_host_list(cf.get_public_agent_ips())})
        return desc

    def delete(self, info):
        stack = self.get_stack(info)
        stack.delete()
        if len(info['temp_resources']) > 0:
            # must wait for stack to be deleted before removing
            # network resources on which it depends
            stack.wait_for_complete()
            self.delete_temp_resources(info['temp_resources'])

    def delete_temp_resources(self, temp_resources):
        if 'key_name' in temp_resources:
            self.boto_wrapper.delete_key_pair(temp_resources['key_name'])
        if 'public_subnet' in temp_resources:
            self.boto_wrapper.delete_subnet(temp_resources['public_subnet'])
        if 'private_subnet' in temp_resources:
            self.boto_wrapper.delete_subnet(temp_resources['private_subnet'])
        if 'gateway' in temp_resources:
            self.boto_wrapper.delete_internet_gateway(temp_resources['gateway'])
        if 'vpc' in temp_resources:
            self.boto_wrapper.delete_vpc(temp_resources['vpc'])

    def ssh_from_config(self, config):
        """
        In order to deploy AWS instances, one must use an SSH key pair that was
        previously created in and downloaded from AWS. The private key cannot be
        obtained after its creation; this helper exists to remove this hassle.

        This method will take the config dict, scan the parameters for KeyName,
        and should KeyName not be found it generate a key and amend the config.
        Returns two dicts: ssh_info and temporary resources. SSH user cannot be
        inferred, so the user must still provide this explicitly via the field
        'private_key_path'

        Thus, there are 4 possible allowable scenarios:
        ### Result: nothing generated, testing possible ###
        ---
        parameters:
          - ParameterKey: KeyName
            ParameterValue: my_key_name
        ssh_info:
          user: foo
          private_key_path: path_to_my_key

        ### Result: key generated, testing possible ###
        ---
        ssh_info:
          user: foo

        ### Result: nothing generated, testing not possible
        ---
        parameters:
          - ParameterKey: KeyName
            ParameterValue: my_key_name

        ### Result: key generated, testing not possible
        ---
        """
        temp_resources = {}
        key_name = None
        private_key = None
        # Native AWS parameters take precedence
        if 'parameters' in config:
            for p in config['parameters']:
                if p['ParameterKey'] == 'KeyName':
                    key_name = p['ParameterValue']
        # check ssh_info data
        if 'ssh_info' in config and 'private_key_path' in config['ssh_info']:
            if key_name is None:
                raise LauncherError('ValidationError', 'If a private_key_path is provided, '
                                    'then the KeyName template parameter must be set')
            private_key = load_string(config['ssh_info']['private_key_path'])
        if not key_name:
            key_name = config['stack_name']
            private_key = self.boto_wrapper.create_key_pair(key_name)
            temp_resources['key_name'] = key_name
            cf_params = config.get('parameters', list())
            cf_params.append({'ParameterKey': 'KeyName', 'ParameterValue': key_name})
            config['parameters'] = cf_params
        user = config.get('ssh_info', dict()).get('user', None)
        ssh_info = {'private_key': private_key, 'user': user}
        if user is None:
            print('Testing not possible; user must be provided under ssh_info in config YAML')
        if private_key is None:
            print('Testing not possible; private_key_path must be provided under ssh_info in config YAML')
        return ssh_info, temp_resources

    def get_stack(self, info):
        try:
            return fetch_stack(info['stack_id'], self.boto_wrapper)
        except Exception as ex:
            raise LauncherError('StackNotFound', None) from ex


def get_launcher(launcher_type, provider_info):
    """Returns a launcher given a launcher type (string) and a dictionary of
    appropriate provier_info
    """
    if launcher_type == 'cloudformation':
        check_keys(provider_info, ['region', 'access_key_id', 'secret_access_key'])
        boto_wrapper = BotoWrapper(
            provider_info['region'], provider_info['access_key_id'], provider_info['secret_access_key'])
        return AwsCloudformationLauncher(boto_wrapper)
    raise LauncherError('UnsupportedAction', 'Launcher type not supported: {}'.format(launcher_type))


def convert_host_list(host_list):
    """ Makes Host tuples more readable when using describe
    """
    return [{'private_ip': h.private_ip, 'public_ip': h.public_ip} for h in host_list]


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
