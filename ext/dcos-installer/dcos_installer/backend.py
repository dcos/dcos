"""
Glue code for logic around calling associated backend
libraries to support the dcos installer.
"""
import logging
import os

import boto3
import botocore.exceptions
import yaml

import gen
import gen.calc
import gen.installer.aws
import release
import release.storage.aws
import release.storage.local
import ssh.validate
from dcos_installer import config_util
from dcos_installer.config import DCOSConfig, stringify_configuration
from dcos_installer.constants import CONFIG_PATH, IP_DETECT_PATH, SSH_KEY_PATH

log = logging.getLogger()


def print_messages(messages):
    for key, error in messages.items():
        log.error('{}: {}'.format(key, error))


def do_configure(config_path=CONFIG_PATH):
    """Returns error code

    :param config_path: path to config.yaml
    :type config_path: string | CONFIG_PATH (genconf/config.yaml)
    """
    messages = do_validate_config(config_path, include_ssh=False)
    if messages:
        print_messages(messages)
        return 1
    else:
        config = DCOSConfig(config_path=config_path)
        config_util.do_configure(config.stringify_configuration())
        return 0


# Taken from: http://docs.aws.amazon.com/general/latest/gr/rande.html#s3_region
# In the same order as that document.
region_to_endpoint = {
    'us-east-1': 's3.amazonaws.com',
    'us-west-1': 's3-us-west-1.amazonaws.com',
    'us-west-2': 's3-us-west-2.amazonaws.com',
    'ap-south-1': 's3.ap-south-1.amazonaws.com',
    'ap-northeast-2': 's3.ap-northeast-2.amazonaws.com',
    'ap-southeast-1': 's3-ap-southeast-1.amazonaws.com',
    'ap-southeast-2': 's3-ap-southeast-2.amazonaws.com',
    'ap-northeast-1': 's3-ap-northeast-1.amazonaws.com',
    'eu-central-1': 's3.eu-central-1.amazonaws.com',
    'eu-west-1': 's3-eu-west-1.amazonaws.com',
    'sa-east-1': 's3-sa-east-1.amazonaws.com'
}


def validate_aws_template_storage_region_name(aws_template_storage_region_name):
    assert aws_template_storage_region_name in region_to_endpoint, \
        "Unsupported AWS region {}. Only {} are supported".format(
            aws_template_storage_region_name,
            region_to_endpoint.keys())


def validate_aws_bucket_access(aws_template_storage_region_name,
                               aws_template_storage_access_key_id,
                               aws_template_storage_secret_access_key,
                               aws_template_storage_bucket,
                               aws_template_storage_bucket_path,
                               aws_template_storage_bucket_path_autocreate):

    session = boto3.session.Session(
        aws_access_key_id=aws_template_storage_access_key_id,
        aws_secret_access_key=aws_template_storage_secret_access_key,
        region_name=aws_template_storage_region_name)

    bucket = session.resource('s3').Bucket(aws_template_storage_bucket)

    try:
        bucket.load()
    except botocore.exceptions.ClientError as ex:
        if ex.response['Error']['Code'] == '404':
            raise AssertionError("s3 bucket {} does not exist".format(aws_template_storage_bucket)) from ex
        raise AssertionError("Unable to access s3 bucket {} in region {}: {}".format(
            aws_template_storage_bucket, aws_template_storage_region_name, ex)) from ex

    # If autocreate is on, then skip ensuring the path exists
    if not aws_template_storage_bucket_path_autocreate:
        try:
            bucket.Object(aws_template_storage_bucket_path).load()
        except botocore.exceptions.ClientError as ex:
            if ex.response['Error']['Code'] == '404':
                raise AssertionError(
                    "path `{}` in bucket `{}` does not exist. Create it or set "
                    "aws_template_storage_bucket_path_autocreate to true".format(
                        aws_template_storage_bucket_path, aws_template_storage_bucket))
            raise AssertionError("Unable to access s3 path {} in bucket {}: {}".format(
                aws_template_storage_bucket_path, aws_template_storage_bucket, ex)) from ex


def calculate_reproducible_artifact_path(config_id):
    return 'config_id/{}'.format(config_id)


def calculate_base_repository_url(
        aws_template_storage_region_name,
        aws_template_storage_bucket,
        aws_template_storage_bucket_path):
    return 'https://{domain}/{bucket}/{path}'.format(
        domain=region_to_endpoint[aws_template_storage_region_name],
        bucket=aws_template_storage_bucket,
        path=aws_template_storage_bucket_path)


# Figure out the s3 bucket url from region + bucket + path
# TODO(cmaloney): Allow using a CDN rather than the raw S3 url, which will allow
# us to use this same logic for both the internal / do_create version and the
# user dcos_generate_config.sh option.
def calculate_cloudformation_s3_url(bootstrap_url, config_id):
    return '{}/config_id/{}'.format(bootstrap_url, config_id)

aws_advanced_entry = {
    # TOOD(cmaloney): Add parameter validation for AWS Advanced template output.
    'validate': [
        lambda aws_template_upload: gen.calc.validate_true_false(aws_template_upload),
        lambda aws_template_storage_bucket_path_autocreate:
            gen.calc.validate_true_false(aws_template_storage_bucket_path_autocreate),
        validate_aws_template_storage_region_name,
        validate_aws_bucket_access
    ],
    'default': {
        'num_masters': '5',
        'aws_template_upload': 'true',
        'aws_template_storage_bucket_path_autocreate': 'true',
        'bootstrap_id': lambda: gen.calc.calculate_environment_variable('BOOTSTRAP_ID')
        # TODO(cmaloney): Add defaults for getting AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY from the
        # environment to set as keys. Not doing for now since they would need to be passed through
        # the `docker run` inside dcos_generate_config.sh
    },
    'must': gen.merge_dictionaries({
        'provider': 'aws',
        'cloudformation_s3_url': calculate_cloudformation_s3_url,
        'bootstrap_url': calculate_base_repository_url,
        'reproducible_artifact_path': calculate_reproducible_artifact_path
    }, gen.installer.aws.groups['master'][1])
}


aws_advanced_parameters = {
    'variables': {
        # TODO(cmaloney): Namespacing would be really handy here...
        'aws_template_storage_bucket',
        'aws_template_storage_bucket_path',
        'aws_template_upload',
        'aws_template_storage_bucket_path_autocreate',
        'cloudformation_s3_url',
        'provider',
        'bootstrap_url',
        'bootstrap_variant',
        'reproducible_artifact_path'
    },
    'sub_scopes': {
        'aws_template_upload': {
            'true': {
                'variables': {
                    'aws_template_storage_access_key_id',
                    'aws_template_storage_secret_access_key',
                    'aws_template_storage_region_name'
                }
            },
            'false': {}
        }
    }
}


# TODO(cmaloney): Make it so validation happens using the provided AWS credentials.
def do_aws_cf_configure():
    """Returns error code

    Generates AWS templates using a custom config.yaml
    """

    # TODO(cmaloney): Move to Config class introduced in https://github.com/dcos/dcos/pull/623
    with open(CONFIG_PATH, 'r') as f:
        config = yaml.load(f)

    aws_config_target = gen.ConfigTarget(aws_advanced_parameters)
    aws_config_target.add_entry(aws_advanced_entry, False)

    gen_config = stringify_configuration(config)
    config_targets = [
        gen.get_dcosconfig_target_and_templates(gen_config, [])[0],
        aws_config_target]

    messages = gen.validate_config_for_targets(config_targets, gen_config)
    # TODO(cmaloney): kill this function and make the API return the structured
    # results api as was always intended rather than the flattened / lossy other
    # format. This will be an  API incompatible change. The messages format was
    # specifically so that there wouldn't be this sort of API incompatibility.
    messages = normalize_config_validation(messages)
    if messages:
        print_messages(messages)
        return 1

    # TODO(cmaloney): This is really hacky but a lot simpler than merging all the config flows into
    # one currently.
    # Get out the calculated arguments and manually move critical calculated ones to the gen_config
    # object.
    # NOTE: the copying across, as well as validation is guaranteed to succeed because we've already
    # done a validation run.
    full_config = gen.calculate_config_for_targets(config_targets, gen_config)
    gen_config['bootstrap_url'] = full_config['bootstrap_url']
    gen_config['provider'] = full_config['provider']
    gen_config['bootstrap_id'] = full_config['bootstrap_id']
    gen_config['cloudformation_s3_url'] = full_config['cloudformation_s3_url']

    # Convert the bootstrap_Variant string we have back to a bootstrap_id as used internally by all
    # the tooling (never has empty string, uses None to say "no variant")
    bootstrap_variant = full_config['bootstrap_variant'] if full_config['bootstrap_variant'] else None

    artifacts = list()
    for built_resource in list(gen.installer.aws.do_create(
            tag='dcos_generate_config.sh --aws-cloudformation',
            build_name='Custom',
            reproducible_artifact_path=full_config['reproducible_artifact_path'],
            variant_arguments={bootstrap_variant: gen_config},
            commit=full_config['dcos_image_commit'],
            all_bootstraps=None)):
        artifacts += release.built_resource_to_artifacts(built_resource)

    artifacts += list(release.make_bootstrap_artifacts(full_config['bootstrap_id'], bootstrap_variant, 'artifacts'))

    # Upload all the artifacts to the config-id path and then print out what
    # the path that should be used is, as well as saving a local json file for
    # easy machine access / processing.
    repository = release.Repository(
        full_config['aws_template_storage_bucket_path'],
        None,
        'config_id/' + full_config['config_id'])

    storage_commands = repository.make_commands({'core_artifacts': [], 'channel_artifacts': artifacts})

    log.warning("Writing local copies to genconf/cloudformation")
    storage_provider = release.storage.local.LocalStorageProvider('genconf/cloudformation')
    release.apply_storage_commands({'local': storage_provider}, storage_commands)

    log.warning(
        "Generated templates locally available at %s",
        "genconf/cloudformation/" + full_config["reproducible_artifact_path"])
    # TODO(cmaloney): Print where the user can find the files locally

    if full_config['aws_template_upload'] == 'false':
        return 0

    storage_provider = release.storage.aws.S3StorageProvider(
        bucket=full_config['aws_template_storage_bucket'],
        object_prefix=None,
        download_url=full_config['cloudformation_s3_url'],
        region_name=full_config['aws_template_storage_region_name'],
        access_key_id=full_config['aws_template_storage_access_key_id'],
        secret_access_key=full_config['aws_template_storage_secret_access_key'])

    log.warning("Uploading to AWS")
    release.apply_storage_commands({'aws': storage_provider}, storage_commands)
    log.warning("AWS CloudFormation templates now available at: {}".format(
        full_config['cloudformation_s3_url']))

    # TODO(cmaloney): Print where the user can find the files in AWS
    # TODO(cmaloney): Dump out a JSON with machine paths to make scripting easier.
    return 1


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
    return _do_validate_config(
        DCOSConfig(config_path=config_path),
        include_ssh=include_ssh)


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
        # Skip if the key isn't in config
        if key not in config:
            continue

        # None indicates any value means this is advanced config.
        # A string indicates the value must match.
        if value is None:
            log.error('Advanced configuration found in config.yaml: {}: value'.format(key, value))
            adv_found[key] = config[key]
        elif value != config[key]:
            log.error('Advanced configuration found in config.yaml: {}: value'.format(key, config[key]))
            adv_found[key] = config[key]

    if adv_found:
        message = "Advanced configuration detected in genconf/config.yaml ({}).\nPlease backup " \
                  "or remove genconf/config.yaml to use the UI installer.".format(adv_found)
        config_type = 'advanced'
    else:
        message = ''
        config_type = 'minimal'

    return {
        'message': message,
        'type': config_type
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
