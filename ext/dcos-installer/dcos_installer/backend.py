"""
Glue code for logic around calling associated backend
libraries to support the dcos installer.
"""
import logging
import os

import gen
import ssh.validate
from dcos_installer import config_util
from dcos_installer.config import DCOSConfig
from dcos_installer.constants import CONFIG_PATH, IP_DETECT_PATH, SSH_KEY_PATH

log = logging.getLogger()


def do_configure(config_path=CONFIG_PATH):
    """Returns error code

    :param config_path: path to config.yaml
    :type config_path: string | CONFIG_PATH (genconf/config.yaml)
    """
    validate_gen = do_validate_config(config_path, include_ssh=False)
    if len(validate_gen) > 0:
        for key, error in validate_gen.items():
            log.error('{}: {}'.format(key, error))
        return 1
    else:
        config = DCOSConfig(config_path=config_path)
        config_util.do_configure(config.stringify_configuration())
        return 0


def write_external_config(data, path, mode=0o644):
    """Returns None. Writes external configuration files (ssh_key, ip-detect).

    :param data: configuration file data
    :type data: string | None

    :param path: path to configuration file
    :type path: str | None

    :param mode: file mode
    :type mode: octal | 0o644
    """
    log.warning('Writing {} with mode {}: {}'.format(path, mode, data))
    if data is not None and data is not "":
        f = open(path, 'w')
        f.write(data)
        os.chmod(path, mode)
    else:
        log.warning('Request to write file {} ignored.'.format(path))
        log.warning('Cowardly refusing to write empty values or None data to disk.')


def create_config_from_post(post_data={}, config_path=CONFIG_PATH):
    """Returns error code and validation messages for only keys POSTed
    to the UI.

    :param config_path: path to config.yaml
    :type config_path: string | CONFIG_PATH (genconf/config.yaml)

    :param post_data: data from POST to UI
    :type post_data: dict | {}
    """
    log.info("Creating new DCOSConfig object from POST data.")

    if 'ssh_key' in post_data:
        write_external_config(post_data['ssh_key'], SSH_KEY_PATH, mode=0o600)

    if 'ip_detect_script' in post_data:
        write_external_config(post_data['ip_detect_script'], IP_DETECT_PATH)

    # TODO (malnick) remove when UI updates are complete
    post_data = remap_post_data_keys(post_data)
    # Create a new configuration object, pass it the config.yaml path and POSTed dictionary.
    # Add in "hidden config" we don't present in the config.yaml, and then create a meta
    # validation dictionary from gen and ssh validation libs.
    # We do not use the already built methods for this since those are used to read the
    # coniguration off disk, here we need to validate the configuration overridees, and
    # return the key and message for the POSTed parameter.
    config = DCOSConfig(config_path=config_path, overrides=post_data)
    validation_messages = _do_validate_config(config, include_ssh=True)

    # Return only keys sent in POST, do not write if validation
    # of config fails.
    validation_err = False

    # Create a dictionary of validation that only includes
    # the messages from keys POSTed for validation.
    post_data_validation = {key: validation_messages[key] for key in validation_messages if key in post_data}

    # If validation is successful, write the data to disk, otherwise, if
    # they keys POSTed failed, do not write to disk.
    if post_data_validation is not None and len(post_data_validation) > 0:
        log.error("POSTed configuration has errors, not writing to disk.")
        for key, value in post_data_validation.items():
            log.error('{}: {}'.format(key, value))
        validation_err = True

    else:
        log.debug("Success! POSTed configuration looks good, writing to disk.")
        config.config_path = config_path
        config.write()

    return validation_err, post_data_validation


def _do_validate_config(config, include_ssh):
    config.update(config_util.get_gen_extra_args())
    user_arguments = config.stringify_configuration()

    config_targets = [gen.get_dcosconfig_target_and_templates(user_arguments, [])[0]]

    if include_ssh:
        config_targets.append(ssh.validate.get_config_target())

    messages = gen.validate_config_for_targets(config_targets, user_arguments)
    # TODO(cmaloney): kill this function and make the API return the structured
    # results api as was always intended rather than the flattened / lossy other
    # format. This will be an  API incompatible change. The messages format was
    # specifically so that there wouldn't be this sort of API incompatibility.
    validation = normalize_config_validation(messages)

    # TODO(cmaloney): Remove the need to remap.
    return remap_validation_keys(validation)


def do_validate_config(config_path=CONFIG_PATH, include_ssh=True):
    """Returns complete validation messages from both SSH and Gen libraries."""
    return _do_validate_config(DCOSConfig(config_path=config_path), include_ssh)


def remap_post_data_keys(post_data):
    """Remap the post_data keys so we return the correct
    values to the UI

    TODO (malnick) remove when UI updates are in.
    """
    remap = {
        'ssh_key': ['ssh_key_path', 'genconf/ssh_key'],
        'ip_detect_script': ['ip_detect_path', 'genconf/ip-detect'],
    }
    for key, value in remap.items():
        if key in post_data:
            post_data[value[0]] = value[1]

    return post_data


def remap_validation_keys(messages):
    """Accepts a complete dictionary of config, remapping the
    keys to ones the UI currently supports.

    TODO (malnick) will remove once UI updates are in place.

    :param messages: dictionary of k,v's containing validation
    :type messages: dict | {}
    """
    if "ssh_key_path" in messages:
        messages["ssh_key"] = messages["ssh_key_path"]

    if "ip_detect_contents" in messages:
        messages['ip_detect_path'] = messages['ip_detect_contents']

    if 'num_masters' in messages:
        messages['master_list'] = messages['num_masters']

    return messages


def normalize_config_validation(messages):
    """Accepts Gen error message format and returns a flattened dictionary
    of validation messages.

    :param messages: Gen validation messages
    :type messages: dict | None
    """
    validation = {}
    if 'errors' in messages:
        for key, errors in messages['errors'].items():
            validation[key] = errors['message']

    if 'unset' in messages:
        for key in messages['unset']:
            validation[key] = 'Must set {}, no way to calculate value.'.format(key)

    return validation


def get_config(config_path=CONFIG_PATH):
    """Returns config.yaml on disk as dict.

    :param config_path: path to config.yaml
    :type config_path: str | CONFIG_PATH (genconf/config.yaml)
    """
    return DCOSConfig(config_path=config_path)


def get_ui_config(config_path=CONFIG_PATH):
    """Returns config.yaml plus externalized config data, which
    includes ssh_key and ip-detect, to the UI.

    :param config_path: path to config.yaml
    :type config_path: str | CONFIG_PATH (genconf/config.yaml)
    """
    config = DCOSConfig(config_path=config_path)
    config.get_external_config()
    config.update(config.external_config)
    return config


def determine_config_type(config_path=CONFIG_PATH):
    """Returns the configuration type to the UI. One of either 'minimal' or
    'advanced'. 'advanced' blocks UI usage.

    :param config_path: path to config.yaml
    :type config_path: str | CONFIG_PATH (genconf/config.yaml)
    """
    # TODO(cmaloney): If the config has any arguments not in the set of possible parameters then
    # the config is always advanced.
    config = get_config(config_path=config_path)
    ctype = 'minimal'
    message = ''
    adv_found = {}
    advanced_cluster_config = {
        "bootstrap_url": 'file:///opt/dcos_install_tmp',
        "docker_remove_delay": None,
        "exhibitor_storage_backend": 'static',
        "gc_delay": None,
        "master_discovery": 'static',
        "roles": None,
        "weights": None
    }
    for key, value in advanced_cluster_config.items():
        if value is None and key in config:
            adv_found[key] = config[key]

        if value is not None and key in config and value != config[key]:
            log.error('Advanced configuration found in config.yaml: {}: value'.format(key, value))
            adv_found[key] = config[key]

    if len(adv_found) > 0:
        message = """Advanced configuration detected in genconf/config.yaml ({}).
 Please backup or remove genconf/config.yaml to use the UI installer.""".format(adv_found)
        ctype = 'advanced'

    return {
        'message': message,
        'type': ctype
    }


def success(config={}):
    """Returns the data for /success/ endpoint.
    :param config_path: path to config.yaml
    :type config_path: str | CONFIG_PATH (genconf/config.yaml)
    """
    code = 200
    msgs = {
        'success': "",
        'master_count': 0,
        'agent_count': 0
    }
    if not config:
        config = get_config()
    master_ips = config.get('master_list', [])
    agent_ips = config.get('agent_list', [])
    if not master_ips or not agent_ips:
        code = 400
        return msgs, code
    msgs['success'] = 'http://{}'.format(master_ips[0])
    msgs['master_count'] = len(master_ips)
    msgs['agent_count'] = len(agent_ips)
    return msgs, code
