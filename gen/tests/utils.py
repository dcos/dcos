"""
Utilities for tests for ``gen``.
"""

import copy
import json

import pkg_resources

import gen
from pkgpanda.util import is_windows

true_false_msg = "Must be one of 'true', 'false'. Got 'foo'."


def make_arguments(new_arguments):
    """
    Fields with default values should not be added in here so that the
    default values are also tested.
    """
    if is_windows:
        ipdetect_script = "ip-detect/aws.ps1"
        ipdetect6_script = "ip-detect/aws6.ps1"
    else:
        ipdetect_script = "ip-detect/aws.sh"
        ipdetect6_script = "ip-detect/aws6.sh"
    arguments = copy.deepcopy({
        'ip_detect_filename': pkg_resources.resource_filename('gen', ipdetect_script),
        'ip6_detect_filename': pkg_resources.resource_filename('gen', ipdetect6_script),
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
        'enable_docker_gc': 'false'})
    arguments.update(new_arguments)
    return arguments


def validate_error(new_arguments, key, message, unset=None):
    assert gen.validate(arguments=make_arguments(new_arguments)) == {
        'status': 'errors',
        'errors': {key: {'message': message}},
        'unset': set() if unset is None else unset,
    }


def validate_success(new_arguments):
    assert gen.validate(arguments=make_arguments(new_arguments)) == {
        'status': 'ok',
    }
