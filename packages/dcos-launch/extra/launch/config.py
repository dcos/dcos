import atexit
import copy
import os

import requests
import yaml

import gen
import launch.util
import ssh.validate
import test_util.aws
import test_util.helpers
from gen.internals import resolve_configuration, Scope, Source, Target, validate_one_of
from pkgpanda.util import load_string, load_yaml, YamlParseError

# DCOS_OSS-802: [gen/dcos_installer] allow using library uncoupled from installer
# dcos_installer.config will directly import gen.build_deploy.util
# which expects to find the image commit in the environment or in
# a directory-local git tree **at import time**. Therefore, the
# environment variable DCOS_IMAGE_COMMIT must be set here.
if 'DCOS_IMAGE_COMMIT' not in os.environ:
    os.environ['DCOS_IMAGE_COMMIT'] = ''
    atexit.register(os.unsetenv, 'DCOS_IMAGE_COMMIT')

import dcos_installer.config  # noqa

# gen.build_deploy.bash expects to be run from the installer or git-tree
# environment and will expect this when resolving the onprem configuration
if 'BOOTSTRAP_VARIANT' not in os.environ:
    os.environ['BOOTSTRAP_VARIANT'] = ''
    atexit.register(os.unsetenv, 'BOOTSTRAP_VARIANT')

# gen.build_deploy.bash expects to be able to get a list of packages
# from a JSON at a hard-coded path. The package list is used for the deploy
# logic of the installer and trivializing it here will have no bearing on
# the onprem config.yaml pre-validation performed in this module
setattr(dcos_installer.config_util, 'installer_latest_complete_artifact', launch.util.stub({'packages': []}))


def expand_path(path: str, relative_dir: str) -> str:
    """ Returns an absolute path
    path: the user-provided path
    relative_dir: the absolute directory to which `path` should be seen as
        relative
    """
    path = os.path.expanduser(path)
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(relative_dir, path))


def expand_filenames(config: dict, config_dir: str) -> dict:
    """ Recursively mutates a config dict so that all keys that end with
    '_filename' will be ensured to be absolute paths
    """
    new_config = copy.deepcopy(config)
    for k, v in new_config.items():
        if isinstance(v, dict):
            new_config[k] = expand_filenames(v, config_dir)
        if not isinstance(v, str):
            continue
        if k.endswith('_filename'):
            new_config[k] = expand_path(v, config_dir)
    return new_config


def yaml_flatten(config: dict) -> dict:
    """ Takes a multi-layered dict and converts it to a single-layer dict by
    converting sub-icts into yaml strings
    """
    new_config = copy.deepcopy(config)
    for k, v in new_config.items():
        if isinstance(v, dict):
            new_config[k] = yaml.dump(v)
    return new_config


def load_config(config_path: str) -> dict:
    try:
        config = load_yaml(config_path)
        return config
    except YamlParseError as ex:
        raise launch.util.LauncherError('InvalidInput', None) from ex
    except FileNotFoundError as ex:
        raise launch.util.LauncherError('MissingConfig', None) from ex


def gen_format_config(config: dict, config_dir: str) -> dict:
    """ path-expands, yaml-flattens, and stringifies user-provided config-dict
    """
    return gen.stringify_configuration(yaml_flatten(expand_filenames(config, config_dir)))


def get_validated_config(config_path: str) -> dict:
    """ Returns validated a finalized argument dictionary for dcos-launch
    """
    config = load_config(config_path)
    config_dir = os.path.dirname(config_path)
    config = gen_format_config(config, config_dir)
    resolver = validate_config(config)
    final_args = gen.get_final_arguments(resolver)
    # TODO DCOS-14196: [gen.internals] disallow extra user provided arguments
    unrecognized_args = set(config.keys()) - set(final_args.keys())
    if len(unrecognized_args) > 0:
        raise launch.util.LauncherError(
            'ValidationError', 'Unrecognized/incompatible arguments: {}'.format(unrecognized_args))
    return final_args


def validate_config(user_config: dict) -> gen.internals.Resolver:
    """ Converts the user config to to a source and evaluates it
    versus the targets and source in this module. Also, catches
    and reformats the validation exception before raising
    """
    sources = [Source(entry), gen.user_arguments_to_source(user_config)]
    try:
        return gen.validate_and_raise(sources, [get_target()])
    except gen.exceptions.ValidationError as ex:
        raise launch.util.LauncherError(
            'ValidationError', pretty_print_validate_error(ex.errors, ex.unset))


def pretty_print_validate_error(errors, unset):
    out = ''
    if errors != {}:
        out = '\nErrors:\n'
        for k, v in errors.items():
            out += '  {}: {}\n'.format(k, v['message'])
    if len(unset) > 0:
        out += '\nUnset arguments:\n'
        for u in unset:
            out += '  ' + u + '\n'
    return out


def get_target():
    """ Targets must never be re-used after its been evaluated by gen, so
    do not define it as a global constant
    """
    aws_platform_target = Target({
        'aws_region',
        'aws_access_key_id',
        'aws_secret_access_key',
        'key_helper',
        'zen_helper',
        'deployment_name'},
        {
            'provider': Scope('provider', {
                'aws': Target({}),
                'azure': Target({}),
                'onprem': Target({}, {
                    'key_helper': Scope('key_helper', {
                        'true': Target({}),
                        'false': Target({'aws_key_name'})
                    })
                })
            })
    })
    azure_platform_target = Target({
        'azure_location',
        'azure_client_id',
        'azure_client_secret',
        'azure_tenant_id',
        'azure_subscription_id',
        'deployment_name',
        'key_helper'})
    template_target = Target({
        'template_url',
        'template_parameters'})
    onprem_target = Target(
        {
            'installer_url',
            'installer_port',
            'num_private_agents',
            'num_public_agents',
            'num_masters',
            'prevalidate_onprem_config',
            'onprem_dcos_config_contents'
        },
        {
            'platform': Scope('platform', {
                'aws': Target({
                    'aws_key_name',
                    'cluster_size',
                    'instance_ami',
                    'instance_type',
                    'admin_location'}),
                'azure': Target({})})})  # Unsupported currently
    return Target({
        'launch_config_version',
        'platform',
        'provider',
        'ssh_port',
        'ssh_private_key',
        'ssh_user'},
        {
            'platform': Scope('platform', {
                'aws': aws_platform_target,
                'azure': azure_platform_target}),
            'provider': Scope('provider', {
                'aws': template_target,
                'azure': template_target,
                'onprem': onprem_target})})


def validate_template_url(template_url):
    assert template_url.startswith('http')


def validate_installer_url(installer_url):
    assert installer_url.startswith('http'), 'Not a valid URL: {}'.format(installer_url)
    assert requests.head(installer_url).status_code == 200


def validate_launch_config_version(launch_config_version):
    assert int(launch_config_version) == 1


def validate_onprem_dcos_config_contents(onprem_dcos_config_contents, num_masters, prevalidate_onprem_config):
    # TODO DCOS-14033: [gen.internals] Source validate functions are global only
    if prevalidate_onprem_config != 'true':
        return
    user_config = yaml.load(onprem_dcos_config_contents)
    # Use the default config in the installer
    config = yaml.load(dcos_installer.config.config_sample)
    config.update(user_config)
    # This field is required and auto-added by installer, so add a dummy here
    if 'bootstrap_id' not in config:
        config['bootstrap_id'] = 'deadbeef'

    # dummy master list to pass validation
    config['master_list'] = [('10.0.0.' + str(i)) for i in range(int(num_masters))]

    # Use the default config in the installer
    sources, targets, templates = gen.get_dcosconfig_source_target_and_templates(
        gen.stringify_configuration(config), list(), [ssh.validate.source, gen.build_deploy.bash.onprem_source])

    # Copy the gen target from dcos_installer/config.py, but instead remove
    # 'ssh_key_path' from the target because the validate fn in ssh_source is
    # too strict I.E. we cannot validate a key if we are going to generate
    # Furthermore, we cannot use the target ssh_key_path as it will automatically
    # invoked the validate fn from ssh/validate.py Luckily, we can instead use
    # the more idiomatic 'ssh_private_key_filename'
    targets.append(Target({
        'ssh_user',
        'ssh_port',
        'master_list',
        'agent_list',
        'public_agent_list',
        'ssh_parallelism',
        'process_timeout'}))

    resolver = resolve_configuration(sources, targets)
    status = resolver.status_dict
    if status['status'] == 'errors':
        raise AssertionError(pretty_print_validate_error(status['errors'], status['unset']))


def calculate_dcos_config_contents(dcos_config, num_masters, ssh_user, ssh_private_key, platform):
    """ Fills in the ssh user, ssh private key and ip-detect script if possible
    Takes the config's local references and converts them into transmittable content
    """
    user_config = yaml.load(dcos_config)
    # Use the default config in the installer for the same experience
    # w.r.t the auto-filled settings
    config = yaml.load(dcos_installer.config.config_sample)
    config.update(user_config)
    config['ssh_user'] = ssh_user
    config['ssh_key'] = ssh_private_key
    for key_name in ['ip_detect_filename', 'ip_detect_public_filename']:
        if key_name in config:
            config[key_name.replace('_filename', '_contents')] = load_string(config[key_name])
            del config[key_name]
    if 'ip_detect_contents' not in config:
        config['ip_detect_contents'] = test_util.helpers.ip_detect_script(platform)
    return yaml.dump(config)


def validate_onprem_provider_platform(provider, platform):
    # TODO DCOS-14033: [gen.internals] Source validate functions are global only
    if provider == 'onprem':
        assert platform != 'azure', '`provider: onprem` is not currently not support on azure'
    else:
        assert platform == provider


def validate_key_helper_support(platform, key_helper):
    # TODO DCOS-14033: [gen.internals] Source validate functions are global only
    if key_helper == 'false':
        return
    assert platform in ('aws', 'azure')


def calculate_ssh_user(os_name, platform):
    if platform == 'aws':
        return test_util.aws.OS_SSH_INFO[os_name].user
    else:
        raise Exception('Cannot yet calculate user for {} platform'.format(platform))


def validate_key_helper_parameters(template_parameters, provider, key_helper):
    # TODO DCOS-14033: [gen.internals] Source validate functions are global only
    if key_helper == 'false':
        return
    if provider == 'aws':
        assert 'KeyName' not in yaml.load(template_parameters), 'key_helper will '\
            'automatically calculate and inject KeyName; do not set this parameter'
    if provider == 'azure':
        assert 'sshRSAPublicKey' not in yaml.load(template_parameters), 'key_helper will '\
            'automatically calculate and inject sshRSAPublicKey; do not set this parameter'


def calculate_instance_count(num_masters, num_private_agents, num_public_agents):
    return str(1 + int(num_masters) + int(num_private_agents) + int(num_public_agents))


def validate_os_name(os_name, platform, provider):
    # TODO DCOS-14033: [gen.internals] Source validate functions are global only
    if provider != 'onprem':
        # the os_name parameter only applies to homogenous clusters that need
        # to be created by dcos-launch for an onprem install. In other cases,
        # the deployment template is parameterized for OS selection
        return
    if platform == 'aws':
        validate_one_of(os_name, list(test_util.aws.OS_SSH_INFO.keys()))
    else:
        raise AssertionError('Support not yet implemented for {} bare cluster'.format(platform))


def calculate_ssh_private_key(ssh_private_key_filename):
    if ssh_private_key_filename == '':
        return launch.util.NO_TEST_FLAG
    return load_string(ssh_private_key_filename)


def calculate_instance_ami(os_name, aws_region):
    return test_util.aws.OS_AMIS[os_name][aws_region]


def validate_key_name(provider, platform, key_helper):
    if provider == 'aws' and platform == 'onprem' and key_helper == 'false':
        raise AssertionError('Either provide `key_name`')


def calculate_cluster_size(num_masters, num_private_agents, num_public_agents):
    # add one for the installer bootstrap host
    return str(1 + int(num_masters) + int(num_private_agents) + int(num_public_agents))


entry = {
    'validate': [
        validate_installer_url,
        validate_launch_config_version,
        validate_onprem_dcos_config_contents,
        validate_key_helper_parameters,
        validate_key_helper_support,
        validate_onprem_provider_platform,
        validate_os_name,
        lambda key_helper: gen.calc.validate_true_false(key_helper),
        lambda zen_helper: gen.calc.validate_true_false(zen_helper),
        lambda provider: validate_one_of(provider, ['aws', 'azure', 'onprem']),
        lambda platform: validate_one_of(platform, ['aws', 'azure']),
    ],
    'default': {
        'ssh_port': '22',
        'ssh_private_key': calculate_ssh_private_key,
        'instance_ami': calculate_instance_ami,
        'os_name': 'cent-os-7-prereqs',
        'key_helper': 'false',
        'zen_helper': 'false'
    },
    'conditional': {
        'provider': {
            'aws': {
                'default': {
                    # allow untest-able deployment
                    'ssh_user': '',
                    'ssh_private_key_filename': ''
                },
                'must': {
                    # TODO DCOS-14048: [gen.internals] allow user providing arguments
                    # for a 'must' if the arguments agree
                    'platform': 'aws'
                }
            },
            'azure': {
                'default': {
                    # allow untest-able deployment
                    'ssh_user': '',
                    'ssh_private_key_filename': ''
                },
                'must': {
                    # TODO DCOS-14048: [gen.internals] allow user providing arguments
                    # for a 'must' if the arguments agree
                    'platform': 'azure'
                }
            },
            'onprem': {
                'default': {
                    'prevalidate_onprem_config': 'false',
                    'num_public_agents': '0',
                    'num_private_agents': '0',
                    'installer_port': '9000',
                    'admin_location': '0.0.0.0/0'
                },
                'must': {
                    'onprem_dcos_config_contents': calculate_dcos_config_contents,
                    'ssh_user': calculate_ssh_user,
                    'cluster_size': calculate_cluster_size
                },
            },
        },
        'key_helper': {
            'true': {
                'must': {
                    # key input not applicable if helper is used
                    'aws_key_name': 'unset',
                    'ssh_private_key_filename': 'unset',
                    'ssh_private_key': 'unset'}},
            'false': {}
        }
    }
}
