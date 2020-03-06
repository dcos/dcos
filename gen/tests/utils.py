"""
Utilities for tests for ``gen``.
"""

import copy
import json

import pkg_resources

import gen

true_false_msg = "Must be one of 'true', 'false'. Got 'foo'."

# MANDATORY_ARGUMENT provides default values for the mandatory configurations
# for test only
MANDATORY_ARGUMENTS = {'calico_network_cidr': '192.168.0.0/16'}


def make_arguments(new_arguments):
    """
    Fields with default values should not be added in here so that the
    default values are also tested.
    """
    arguments = copy.deepcopy({
        'ip_detect_filename': pkg_resources.resource_filename('gen', 'ip-detect/aws.sh'),
        'ip6_detect_filename': pkg_resources.resource_filename('gen', 'ip-detect/aws6.sh'),
        'bootstrap_id': '123',
        'package_ids': json.dumps(['package--version']),
        'exhibitor_zk_path': '/dcos',
        'master_discovery': 'static',
        'platform': 'aws',
        'provider': 'onprem',
        'exhibitor_zk_hosts': '52.37.205.237:2181',
        'resolvers': '["8.8.8.8", "8.8.4.4"]',
        'master_list': '["52.37.192.49", "52.37.181.230", "52.37.163.105"]',
        'exhibitor_storage_backend': 'zookeeper',
        'bootstrap_url': 'file:///opt/dcos_install_tmp',
        'cluster_name': 'Mesosphere: The Data Center Operating System',
        'bootstrap_variant': '',
        'oauth_available': 'true',
        'oauth_enabled': 'true',
        'enable_docker_gc': 'false',
        'calico_network_cidr': '192.168.0.0/16'})
    arguments.update(new_arguments)
    return arguments


def validate_error(new_arguments, key, message, unset=None):
    arguments = make_arguments(new_arguments)
    validate_result = gen.validate(arguments=arguments)
    assert validate_result == {
        'status': 'errors',
        'errors': {key: {'message': message}},
        'unset': set() if unset is None else unset,
    }


def validate_error_multikey(new_arguments, keys, message, unset=None):
    assert gen.validate(arguments=make_arguments(new_arguments)) == {
        'status': 'errors',
        'errors': {key: {'message': message} for key in keys},
        'unset': set() if unset is None else unset,
    }


def validate_success(new_arguments):
    assert gen.validate(arguments=make_arguments(new_arguments)) == {
        'status': 'ok',
    }


def generate_wrapper(
        arguments,
        extra_templates=list(),
        extra_sources=list(),
        extra_targets=list()):

    for config, val in MANDATORY_ARGUMENTS.items():
        if config not in arguments:
            arguments[config] = val

    return gen.generate(
        arguments, extra_templates, extra_sources, extra_targets)
