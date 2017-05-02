import copy
import json

import pkg_resources
import pytest

import gen


true_false_msg = "Must be one of 'true', 'false'. Got 'foo'."

dns_forward_zones_str = """\
[["a.contoso.com", [["1.1.1.1", 53], \
                    ["2.2.2.2", 53]]], \
 ["b.contoso.com", [["3.3.3.3", 53], \
                    ["4.4.4.4", 53]]]] \
"""

bad_dns_forward_zones_str = """\
[["a.contoso.com", [[1, 53], \
                    ["2.2.2.2", 53]]], \
 ["b.contoso.com", [["3.3.3.3", 53], \
                    ["4.4.4.4", 53]]]] \
"""


@pytest.fixture
def make_arguments(new_arguments):
    """
    Fields with default values should not be added in here so that the
    default values are also tested.
    """
    arguments = copy.deepcopy({
        'ip_detect_filename': pkg_resources.resource_filename('gen', 'ip-detect/aws.sh'),
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


def validate_success(new_arguments, key):
    assert gen.validate(arguments=make_arguments(new_arguments)) == {
        'status': 'ok',
    }


def validate_error_multikey(new_arguments, keys, message, unset=None):
    assert gen.validate(arguments=make_arguments(new_arguments)) == {
        'status': 'errors',
        'errors': {key: {'message': message} for key in keys},
        'unset': set() if unset is None else unset,
    }


def validate_ok(new_arguments):
    assert gen.validate(arguments=make_arguments(new_arguments)) == {
        'status': 'ok',
    }


def test_invalid_telemetry_enabled():
    err_msg = "Must be one of 'true', 'false'. Got 'foo'."
    validate_error(
        {'telemetry_enabled': 'foo'},
        'telemetry_enabled',
        err_msg)


def test_invalid_ports():
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


def test_dns_bind_ip_blacklist():
    test_ips = '["52.37.192.49", "52.37.181.230", "52.37.163.105"]'

    validate_success(
        {'dns_bind_ip_blacklist': test_ips},
        'dns_bind_ip_blacklist')


def test_dns_forward_zones():
    zones = dns_forward_zones_str
    bad_zones = bad_dns_forward_zones_str
    err_msg = 'Invalid "dns_forward_zones": 1 not a valid IP address'

    validate_success(
        {'dns_forward_zones': zones},
        'dns_forward_zones')

    validate_error(
        {'dns_forward_zones': bad_zones},
        'dns_forward_zones',
        err_msg)


def test_invalid_ipv4():
    test_ips = '["52.37.192.49", "52.37.181.230", "foo", "52.37.163.105", "bar"]'
    err_msg = "Invalid IPv4 addresses in list: foo, bar"

    validate_error(
        {'master_list': test_ips},
        'master_list',
        err_msg)

    validate_error(
        {'dns_bind_ip_blacklist': test_ips},
        'dns_bind_ip_blacklist',
        err_msg)

    validate_error(
        {'resolvers': test_ips},
        'resolvers',
        err_msg)


def test_invalid_zk_path():
    validate_error(
        {'exhibitor_zk_path': 'bad/path'},
        'exhibitor_zk_path',
        "Must be of the form /path/to/znode")


def test_invalid_zk_hosts():
    validate_error(
        {'exhibitor_zk_hosts': 'zk://10.10.10.10:8181'},
        'exhibitor_zk_hosts',
        "Must be of the form `host:port,host:port', not start with zk://")


def test_invalid_bootstrap_url():
    validate_error(
        {'bootstrap_url': '123abc/'},
        'bootstrap_url',
        "Must not end in a '/'")


def test_validate_duplicates():
    test_ips = '["10.0.0.1", "10.0.0.2", "10.0.0.1"]'
    err_msg = 'List cannot contain duplicates: 10.0.0.1 appears 2 times'

    validate_error(
        {'master_list': test_ips},
        'master_list',
        err_msg)

    validate_error(
        {'dns_bind_ip_blacklist': test_ips},
        'dns_bind_ip_blacklist',
        err_msg)


def test_invalid_oauth_enabled():
    validate_error(
        {'oauth_enabled': 'foo'},
        'oauth_enabled',
        true_false_msg)


def test_cluster_docker_credentials():
    validate_error(
        {'cluster_docker_credentials': 'foo'},
        'cluster_docker_credentials',
        "Must be valid JSON. Got: foo")

    validate_error(
        {'cluster_docker_credentials_dcos_owned': 'foo'},
        'cluster_docker_credentials_dcos_owned',
        true_false_msg)


def test_exhibitor_storage_master_discovery():
    msg_master_discovery = "When master_discovery is not static, exhibitor_storage_backend must be " \
        "non-static. Having a variable list of master which are discovered by agents using the " \
        "master_discovery method but also having a fixed known at install time static list of " \
        "master ips doesn't `master_http_load_balancer` then exhibitor_storage_backend must not " \
        "be static."

    validate_ok({
        'exhibitor_storage_backend': 'static',
        'master_discovery': 'static'})
    validate_ok({
        'exhibitor_storage_backend': 'aws_s3',
        'master_discovery': 'master_http_loadbalancer',
        'aws_region': 'foo',
        'exhibitor_address': 'http://foobar',
        'exhibitor_explicit_keys': 'false',
        'num_masters': '5',
        's3_bucket': 'baz',
        's3_prefix': 'mofo'})
    validate_ok({
        'exhibitor_storage_backend': 'aws_s3',
        'master_discovery': 'static',
        'exhibitor_explicit_keys': 'false',
        's3_bucket': 'foo',
        'aws_region': 'bar',
        's3_prefix': 'baz'})
    validate_error_multikey(
        {'exhibitor_storage_backend': 'static',
         'master_discovery': 'master_http_loadbalancer'},
        ['exhibitor_storage_backend', 'master_discovery'],
        msg_master_discovery,
        unset={'exhibitor_address', 'num_masters'})


def test_validate_default_overlay_network_name():
    msg = "Default overlay network name does not reference a defined overlay network: foo"
    validate_error_multikey(
        {'dcos_overlay_network': json.dumps({
            'vtep_subnet': '44.128.0.0/20',
            'vtep_mac_oui': '70:B3:D5:00:00:00',
            'overlays': [{
                'name': 'bar',
                'subnet': '1.1.1.0/24',
                'prefix': 24
            }],
        }), 'dcos_overlay_network_default_name': 'foo'},
        ['dcos_overlay_network_default_name', 'dcos_overlay_network'],
        msg)


# TODO(cmaloney): Add tests that specific config leads to specific files in specific places at install time.
