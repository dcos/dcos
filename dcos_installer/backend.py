"""
Glue code for logic around calling associated backend
libraries to support the dcos installer.
"""
import json
import logging
import os

import botocore.exceptions

import gen
import gen.build_deploy.aws
import gen.calc
import release
import release.storage.aws
import release.storage.local
from dcos_installer import config_util, upgrade
from dcos_installer.config import (
    Config,
    normalize_config_validation,
    normalize_config_validation_exception,
)
from dcos_installer.constants import CONFIG_PATH, GENCONF_DIR
from gen.exceptions import ExhibitorTLSBootstrapError, ValidationError

log = logging.getLogger()


def print_messages(messages):
    for key, error in messages.items():
        log.error('{}: {}'.format(key, error))


def do_configure(config_path=CONFIG_PATH):
    """Returns error code

    :param config_path: path to config.yaml
    :type config_path: string | CONFIG_PATH (genconf/config.yaml)
    """
    config = Config(config_path)

    try:
        gen_out = config_util.onprem_generate(config)
    except ValidationError as e:
        validation = normalize_config_validation_exception(e)
        print_messages(validation)
        return 1
    except ExhibitorTLSBootstrapError as e:
        log.error('Failed to bootstrap Exhibitor TLS')
        for i, error in enumerate(e.errors):
            return log.error("{}: {}".format(i + 1, error))
        return 1
    config_util.make_serve_dir(gen_out)

    return 0


def generate_node_upgrade_script(installed_cluster_version, config_path=CONFIG_PATH):

    if installed_cluster_version is None:
        print('Must provide the version of the cluster upgrading from')
        return 1

    config = Config(config_path)
    try:
        gen_out = config_util.onprem_generate(config)
    except ValidationError as e:
        validation = normalize_config_validation_exception(e)
        print_messages(validation)
        return 1
    except ExhibitorTLSBootstrapError as e:
        log.error('Failed to bootstrap Exhibitor TLS')
        for i, error in enumerate(e.errors):
            return log.error("{}: {}".format(i + 1, error))
        return 1

    config_util.make_serve_dir(gen_out)

    # generate the upgrade script
    upgrade.generate_node_upgrade_script(gen_out, installed_cluster_version)

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
    'sa-east-1': 's3-sa-east-1.amazonaws.com',
    'us-gov-west-1': 's3-us-gov-west-1.amazonaws.com'
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

    session = release.storage.aws.get_aws_session(
        aws_template_storage_access_key_id,
        aws_template_storage_secret_access_key,
        aws_template_storage_region_name)

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


def calculate_base_repository_url(
        aws_template_storage_region_name,
        aws_template_storage_bucket,
        aws_template_storage_bucket_path):
    return 'https://{domain}/{bucket}/{path}'.format(
        domain=region_to_endpoint[aws_template_storage_region_name],
        bucket=aws_template_storage_bucket,
        path=aws_template_storage_bucket_path)


def calculate_aws_template_storage_region_name(
        aws_template_storage_access_key_id,
        aws_template_storage_secret_access_key,
        aws_template_storage_bucket):

    session = release.storage.aws.get_aws_session(
        aws_template_storage_access_key_id,
        aws_template_storage_secret_access_key)

    try:
        location_info = session.client('s3').get_bucket_location(Bucket=aws_template_storage_bucket)
        loc = location_info["LocationConstraint"]
        if loc is None or loc.strip() == "":
            # If a buckets region is in fact 'us-east-1' the response from the api will actually be an empty value?!
            # Rather than returning the empty value on to we set it to 'us-east-1'.
            # See http://docs.aws.amazon.com/AmazonS3/latest/API/RESTBucketGETlocation.html#RESTBucketGETlocation-responses-response-elements  # noqa
            return "us-east-1"
        else:
            return loc
    except botocore.exceptions.ClientError as ex:
        if ex.response['Error']['Code'] == '404':
            raise AssertionError("s3 bucket {} does not exist".format(aws_template_storage_bucket)) from ex
        raise AssertionError("Unable to determine region location of s3 bucket {}: {}".format(
            aws_template_storage_bucket, ex)) from ex


aws_advanced_source = gen.internals.Source({
    # TODO(cmaloney): Add parameter validation for AWS Advanced template output.
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
        'bootstrap_id': lambda: gen.calc.calculate_environment_variable('BOOTSTRAP_ID'),
        # TODO(cmaloney): Add defaults for getting AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY from the
        # environment to set as keys. Not doing for now since they would need to be passed through
        # the `docker run` inside dcos_generate_config.sh
        'aws_template_storage_access_key_id': '',
        'aws_template_storage_secret_access_key': '',
    },
    'must': {
        'provider': 'aws',
        'package_ids': lambda bootstrap_variant: json.dumps(
            config_util.installer_latest_complete_artifact(bootstrap_variant)['packages']
        ),
        'bootstrap_url': calculate_base_repository_url,
    },
    'secret': [
        'aws_template_storage_access_key_id',
        'aws_template_storage_secret_access_key',
    ],
    'conditional': {
        'aws_template_upload': {
            'true': {
                'default': {
                    'aws_template_storage_region_name': calculate_aws_template_storage_region_name
                }
            },
            'false': {}
        }
    }
})


def get_aws_advanced_target():
    return gen.internals.Target(
        variables={
            # TODO(cmaloney): Namespacing would be really handy here...
            'aws_template_storage_bucket',
            'aws_template_storage_bucket_path',
            'aws_template_upload',
            'aws_template_storage_bucket_path_autocreate',
            'provider',
            'bootstrap_url',
            'bootstrap_variant',
            'package_ids'},
        sub_scopes={
            'aws_template_upload': gen.internals.Scope(
                name='aws_template_upload',
                cases={
                    'true': gen.internals.Target({
                        'aws_template_storage_access_key_id',
                        'aws_template_storage_secret_access_key',
                        'aws_template_storage_region_name'
                    }),
                    'false': gen.internals.Target()
                }
            )
        }
    )


# TODO(cmaloney): Make it so validation happens using the provided AWS credentials.
def do_aws_cf_configure():
    """Returns error code

    Generates AWS templates using a custom config.yaml
    """

    # TODO(cmaloney): Move to Config class introduced in https://github.com/dcos/dcos/pull/623
    config = Config(CONFIG_PATH)

    # This process is usually ran from a docker container where default boto3 credential
    # method may fail and as such, we allow passing these creds explicitly
    if 'aws_template_storage_access_key_id' in config:
        os.environ['AWS_ACCESS_KEY_ID'] = config['aws_template_storage_access_key_id']
    if 'aws_template_storage_secret_access_key' in config:
        os.environ['AWS_SECRET_ACCESS_KEY'] = config['aws_template_storage_secret_access_key']
    if 'aws_template_storage_region_name' in config:
        os.environ['AWS_DEFAULT_REGION'] = config['aws_template_storage_region_name']

    gen_config = config.as_gen_format()

    extra_sources = [
        gen.build_deploy.aws.aws_base_source,
        aws_advanced_source,
        gen.build_deploy.aws.groups['master'][1]]

    sources, targets, _ = gen.get_dcosconfig_source_target_and_templates(gen_config, [], extra_sources)
    targets.append(get_aws_advanced_target())
    resolver = gen.internals.resolve_configuration(sources, targets)
    # TODO(cmaloney): kill this function and make the API return the structured
    # results api as was always intended rather than the flattened / lossy other
    # format. This will be an  API incompatible change. The messages format was
    # specifically so that there wouldn't be this sort of API incompatibility.
    messages = normalize_config_validation(resolver.status_dict)
    if messages:
        print_messages(messages)
        return 1

    # TODO(cmaloney): This is really hacky but a lot simpler than merging all the config flows into
    # one currently.
    # Get out the calculated arguments and manually move critical calculated ones to the gen_config
    # object.
    # NOTE: the copying across, as well as validation is guaranteed to succeed because we've already
    # done a validation run.
    full_config = {k: v.value for k, v in resolver.arguments.items()}

    # Calculate the config ID and values that depend on it.
    config_id = gen.get_config_id(full_config)
    reproducible_artifact_path = 'config_id/{}'.format(config_id)
    cloudformation_s3_url = '{}/config_id/{}'.format(full_config['bootstrap_url'], config_id)
    cloudformation_s3_url_full = '{}/cloudformation'.format(cloudformation_s3_url)

    # TODO(cmaloney): Switch to using the targets
    gen_config['bootstrap_url'] = full_config['bootstrap_url']
    gen_config['provider'] = full_config['provider']
    gen_config['bootstrap_id'] = full_config['bootstrap_id']
    gen_config['package_ids'] = full_config['package_ids']
    gen_config['cloudformation_s3_url_full'] = cloudformation_s3_url_full

    # Convert the bootstrap_Variant string we have back to a bootstrap_id as used internally by all
    # the tooling (never has empty string, uses None to say "no variant")
    bootstrap_variant = full_config['bootstrap_variant'] if full_config['bootstrap_variant'] else None

    artifacts = list()
    for built_resource in list(gen.build_deploy.aws.do_create(
            tag='dcos_generate_config.sh --aws-cloudformation',
            build_name='Custom',
            reproducible_artifact_path=reproducible_artifact_path,
            variant_arguments={bootstrap_variant: gen_config},
            commit=full_config['dcos_image_commit'],
            all_completes=None)):
        artifacts += release.built_resource_to_artifacts(built_resource)

    artifacts += list(release.make_bootstrap_artifacts(
        full_config['bootstrap_id'],
        json.loads(full_config['package_ids']),
        bootstrap_variant,
        'artifacts',
    ))

    for package_id in json.loads(full_config['package_ids']):
        package_filename = release.make_package_filename(package_id)
        artifacts.append({
            'reproducible_path': package_filename,
            'local_path': 'artifacts/' + package_filename,
        })

    # Upload all the artifacts to the config-id path and then print out what
    # the path that should be used is, as well as saving a local json file for
    # easy machine access / processing.
    repository = release.Repository(
        full_config['aws_template_storage_bucket_path'],
        None,
        'config_id/' + config_id)

    storage_commands = repository.make_commands({'core_artifacts': [], 'channel_artifacts': artifacts})

    cf_dir = GENCONF_DIR + '/cloudformation'
    log.warning("Writing local copies to {}".format(cf_dir))
    storage_provider = release.storage.local.LocalStorageProvider(cf_dir)
    release.apply_storage_commands({'local': storage_provider}, storage_commands)

    log.warning(
        "Generated templates locally available at %s",
        cf_dir + "/" + reproducible_artifact_path)
    # TODO(cmaloney): Print where the user can find the files locally

    if full_config['aws_template_upload'] == 'false':
        return 0

    storage_provider = release.storage.aws.S3StorageProvider(
        bucket=full_config['aws_template_storage_bucket'],
        object_prefix=None,
        download_url=cloudformation_s3_url,
        region_name=full_config['aws_template_storage_region_name'],
        access_key_id=full_config['aws_template_storage_access_key_id'],
        secret_access_key=full_config['aws_template_storage_secret_access_key'])

    log.warning("Uploading to AWS")
    release.apply_storage_commands({'aws': storage_provider}, storage_commands)
    log.warning("AWS CloudFormation templates now available at: {}".format(cloudformation_s3_url))

    # TODO(cmaloney): Print where the user can find the files in AWS
    # TODO(cmaloney): Dump out a JSON with machine paths to make scripting easier.
    return 0


def determine_config_type(config_path=CONFIG_PATH):
    """Returns the configuration type to the UI. One of either 'minimal' or
    'advanced'. 'advanced' blocks UI usage.

    :param config_path: path to config.yaml
    :type config_path: str | CONFIG_PATH (genconf/config.yaml)
    """
    # TODO(cmaloney): If the config has any arguments not in the set of possible parameters then
    # the config is always advanced.
    config = Config(config_path)
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
        message = (
            "Advanced configuration detected in {config_path} ({adv_found}).\nPlease backup "
            "or remove {config_path} to use the UI installer.".format(
                config_path=CONFIG_PATH,
                adv_found=adv_found,
            )
        )
        config_type = 'advanced'
    else:
        message = ''
        config_type = 'minimal'

    return {
        'message': message,
        'type': config_type
    }


def success(config: Config):
    """Returns the data for /success/ endpoint.
    :param config_path: path to config.yaml
    :type config_path: str | CONFIG_PATH (genconf/config.yaml)
    """
    master_ips = config.hacky_default_get('master_list', [])
    agent_ips = config.hacky_default_get('agent_list', [])

    code = 200
    msgs = {
        'success': "",
        'master_count': 0,
        'agent_count': 0
    }
    if not master_ips or not agent_ips:
        code = 400
        return msgs, code
    msgs['success'] = 'http://{}'.format(master_ips[0])
    msgs['master_count'] = len(master_ips)
    msgs['agent_count'] = len(agent_ips)
    return msgs, code
