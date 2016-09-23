import copy

import pkg_resources
import pytest

import gen


def validate_helper(arguments):
    return gen.validate(arguments=arguments)


@pytest.fixture
def default_arguments():
    return copy.deepcopy({
        'ip_detect_filename': pkg_resources.resource_filename('gen', 'ip-detect/aws.sh'),
        'bootstrap_id': '123',
        'exhibitor_zk_path': '/dcos',
        'master_discovery': 'static',
        'provider': 'onprem',
        'exhibitor_zk_hosts': '52.37.205.237:2181',
        'resolvers': '["8.8.8.8", "8.8.4.4"]',
        'master_list': '["52.37.192.49", "52.37.181.230", "52.37.163.105"]',
        'exhibitor_storage_backend': 'zookeeper',
        'bootstrap_url': 'file:///opt/dcos_install_tmp',
        'cluster_name': 'Mesosphere: The Data Center Operating System',
        'bootstrap_variant': '',
        'oauth_available': 'true',
        'oauth_enabled': 'true'})


def validate_error(new_arguments, key, message):
    arguments = default_arguments()
    arguments.update(new_arguments)
    expected = {
        'status': 'errors',
        'errors': {
            key: {
                'message': message
            }
        },
        'unset': set(),
    }
    validated = validate_helper(arguments)
    assert validated['status'] == 'errors'
    assert validated == expected


def test_invalid_telemetry_enabled(default_arguments):
    err_msg = "Must be one of 'true', 'false'. Got 'foo'."
    validate_error(
        {'telemetry_enabled': 'foo'},
        'telemetry_enabled',
        err_msg)


def test_invalid_ports(default_arguments):
    test_bad_range = '["52.37.192.49", "52.37.181.230:53", "52.37.163.105:65536"]'
    range_err_msg = "Must be between 1 and 65535 inclusive"
    test_bad_value = '["52.37.192.49", "52.37.181.230:53", "52.37.163.105:abc"]'
    value_err_msg = "Must be an integer but got a str: abc"

    validate_error(
        {'resolvers': test_bad_range},
        'resolvers',
        range_err_msg)

    validate_error(
        {'resolvers': test_bad_value},
        'resolvers',
        value_err_msg)


def test_invalid_ipv4(default_arguments):
    test_ips = '["52.37.192.49", "52.37.181.230", "foo", "52.37.163.105", "bar"]'
    err_msg = "Invalid IPv4 addresses in list: foo, bar"
    validate_error(
        {'master_list': test_ips},
        'master_list',
        err_msg)

    validate_error(
        {'resolvers': test_ips},
        'resolvers',
        err_msg)


def test_invalid_zk_path(default_arguments):
    validate_error(
        {'exhibitor_zk_path': 'bad/path'},
        'exhibitor_zk_path',
        "Must be of the form /path/to/znode")


def test_invalid_zk_hosts(default_arguments):
    validate_error(
        {'exhibitor_zk_hosts': 'zk://10.10.10.10:8181'},
        'exhibitor_zk_hosts',
        "Must be of the form `host:port,host:port', not start with zk://")


def test_invalid_bootstrap_url(default_arguments):
    validate_error(
        {'bootstrap_url': '123abc/'},
        'bootstrap_url',
        "Must not end in a '/'")


def test_validate_duplicates(default_arguments):
    validate_error(
        {'master_list': '["10.0.0.1", "10.0.0.2", "10.0.0.1"]'},
        'master_list',
        'List cannot contain duplicates: 10.0.0.1 appears 2 times')


def test_invalid_oauth_enabled(default_arguments):
    validate_error(
        {'oauth_enabled': 'foo'},
        'oauth_enabled',
        "Must be one of 'true', 'false'. Got 'foo'.")
