import os

import cerberus
import yaml

import launch.util
import test_util.aws
import test_util.helpers


def expand_path(path: str, relative_dir: str) -> str:
    """ Returns an absolute path by performing '~' and '..' substitution target path

    path: the user-provided path
    relative_dir: the absolute directory to which `path` should be seen as
        relative
    """
    path = os.path.expanduser(path)
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(relative_dir, path))


def load_config(config_path: str) -> dict:
    try:
        with open(config_path) as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as ex:
        raise launch.util.LauncherError('InvalidYaml', None) from ex
    except FileNotFoundError as ex:
        raise launch.util.LauncherError('MissingConfig', None) from ex


def validate_url(field, value, error):
    if not value.startswith('http'):
        error(field, 'Not a valid HTTP URL')


def load_ssh_private_key(doc):
    if doc.get('key_helper') == 'true':
        return 'unset'
    if 'ssh_private_key_filename' not in doc:
        return launch.util.NO_TEST_FLAG
    return launch.util.load_string(doc['ssh_private_key_filename'])


class LaunchValidator(cerberus.Validator):
    """ Needs to use unintuitive pattern so that child validator can be created
    for validated the nested dcos_config
    """
    def __init__(self, *args, **kwargs):
        super(LaunchValidator, self).__init__(*args, **kwargs)
        if 'config_dir' in kwargs:
            self.config_dir = kwargs['config_dir']

    def _normalize_coerce_expand_local_path(self, value):
        return expand_path(value, self.config_dir)


def expand_error_dict(errors: dict) -> str:
    message = ''
    for key, errors in errors.items():
        sub_message = 'Field: {}, Errors: '.format(key)
        for e in errors:
            if isinstance(e, dict):
                sub_message += expand_error_dict(e)
            else:
                sub_message += e
            sub_message += '\n'
        message += sub_message
    return message


def raise_errors(validator: LaunchValidator):
    message = expand_error_dict(validator.errors)
    raise launch.util.LauncherError('ValidationError', message)


def get_validated_config(config_path: str) -> dict:
    """ Returns validated a finalized argument dictionary for dcos-launch
    Given the huge range of configuration space provided by this configuration
    file, it must be processed in three steps (common, provider-specifc,
    platform-specific)
    """
    config = load_config(config_path)
    config_dir = os.path.dirname(config_path)
    # validate against the fields common to all configs
    basic_validator = LaunchValidator(COMMON_SCHEMA, config_dir=config_dir, allow_unknown=True)
    if not basic_validator.validate(config):
        raise_errors(basic_validator)

    # add provider specific information to the basic validator
    provider = basic_validator.normalized(config)['provider']
    if provider == 'onprem':
        basic_validator.schema.update(ONPREM_DEPLOY_COMMON_SCHEMA)
    else:
        basic_validator.schema.update(TEMPLATE_DEPLOY_COMMON_SCHEMA)

    # validate again before attempting to add platform information
    if not basic_validator.validate(config):
        raise_errors(basic_validator)

    # use the intermediate provider-validated config to add the platform schema
    platform = basic_validator.normalized(config)['platform']
    if platform == 'aws':
        basic_validator.schema.update(AWS_PLATFORM_SCHEMA)
        if provider == 'onprem':
            basic_validator.schema.update(AWS_ONPREM_SCHEMA)
    elif platform == 'azure':
        basic_validator.schema.update(AZURE_PLATFORM_SCHEMA)
    else:
        raise NotImplementedError()

    # create a strict validator with our final schema and process it
    final_validator = LaunchValidator(basic_validator.schema, config_dir=config_dir, allow_unknown=False)
    if not final_validator.validate(config):
        raise_errors(final_validator)
    return final_validator.normalized(config)


COMMON_SCHEMA = {
    'deployment_name': {
        'type': 'string',
        'required': True},
    'provider': {
        'type': 'string',
        'required': True,
        'allowed': [
            'aws',
            'azure',
            'onprem']},
    'launch_config_version': {
        'type': 'integer',
        'required': True,
        'allowed': [1]},
    'ssh_port': {
        'type': 'integer',
        'required': False,
        'default': 22},
    'ssh_private_key_filename': {
        'type': 'string',
        'coerce': 'expand_local_path',
        'required': False},
    'ssh_private_key': {
        'type': 'string',
        'required': False,
        'default_setter': load_ssh_private_key},
    'ssh_user': {
        'type': 'string',
        'required': False,
        'default': 'core'},
    'key_helper': {
        'type': 'boolean',
        'default': False}}


AWS_PLATFORM_SCHEMA = {
    'aws_region': {
        'type': 'string',
        'required': True},
    'aws_access_key_id': {
        'type': 'string',
        'required': True},
    'aws_secret_access_key': {
        'type': 'string',
        'required': True},
    'zen_helper': {
        'type': 'boolean',
        'default': False}}


AZURE_PLATFORM_SCHEMA = {
    'azure_location': {
        'type': 'string',
        'required': True},
    'azure_client_id': {
        'type': 'string',
        'required': True},
    'azure_client_secret': {
        'type': 'string',
        'required': True},
    'azure_tenant_id': {
        'type': 'string',
        'required': True},
    'azure_subscription_id': {
        'type': 'string',
        'required': True}}


TEMPLATE_DEPLOY_COMMON_SCHEMA = {
    # platform MUST be equal to provider when using templates
    'platform': {
        'type': 'string',
        'readonly': True,
        'default_setter': lambda doc: doc['provider']},
    'template_url': {
        'type': 'string',
        'required': True,
        'validator': validate_url},
    'template_parameters': {
        'type': 'dict',
        'required': True}}


ONPREM_DEPLOY_COMMON_SCHEMA = {
    'platform': {
        'type': 'string',
        'required': True,
        'allowed': ['aws']},
    'installer_url': {
        'validator': validate_url,
        'type': 'string',
        'required': True},
    'installer_port': {
        'type': 'integer',
        'default': 9000},
    'num_private_agents': {
        'type': 'integer',
        'required': True,
        'min': 0},
    'num_public_agents': {
        'type': 'integer',
        'required': True,
        'min': 0},
    'num_masters': {
        'type': 'integer',
        'allowed': [1, 3, 5, 7, 9],
        'required': True},
    'os_name': {
        'type': 'string',
        # not required because machine image can be set directly
        'required': False,
        'default': 'cent-os-7-prereqs',
        # TODO: This is AWS specific; move when support expands to other platofmrs
        'allowed': list(test_util.aws.OS_SSH_INFO.keys())},
    'ssh_user': {
        'required': True,
        'type': 'string',
        'default_setter': lambda doc: test_util.aws.OS_SSH_INFO[doc['os_name']].user},
    'dcos_config': {
        'type': 'dict',
        'required': True,
        'allow_unknown': True,
        'schema': {
            'ip_detect_filename': {
                'coerce': 'expand_local_path',
                'excludes': 'ip_detect_content'},
            'ip_detect_public_filename': {
                'coerce': 'expand_local_path',
                'excludes': 'ip_detect_public_content'},
            'ip_detect_contents': {
                'excludes': 'ip_detect_filename'},
            'ip_detect_public_contents': {
                'excludes': 'ip_detect_public_filename'},
            # currently, these values cannot be set by a user, only by the launch process
            'master_list': {'readonly': True},
            'agent_list': {'readonly': True},
            'public_agent_list': {'readonly': True}}}}


AWS_ONPREM_SCHEMA = {
    'aws_key_name': {
        'type': 'string',
        'dependencies': {
            'key_helper': False}},
    'instance_ami': {
        'type': 'string',
        'required': True,
        'default_setter': lambda doc: test_util.aws.OS_AMIS[doc['os_name']][doc['aws_region']]},
    'instance_type': {
        'type': 'string',
        'required': True},
    'admin_location': {
        'type': 'string',
        'required': True,
        'default': '0.0.0.0/0'}}
