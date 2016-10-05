import collections
import ipaddress
import json
import os
import socket
import textwrap
from math import floor
from subprocess import check_output

import yaml

import gen.aws.calc
import gen.azure.calc
import pkgpanda.exceptions
from pkgpanda import PackageId
from pkgpanda.build import hash_checkout


def type_str(value):
    return type(value).__name__


def check_duplicates(items: list):
    counter = collections.Counter(items)
    duplicates = dict(filter(lambda x: x[1] > 1, counter.items()))
    assert not duplicates, 'List cannot contain duplicates: {}'.format(
        ', '.join('{} appears {} times'.format(*item) for item in duplicates.items()))


# TODO (cmaloney): Python 3.5, add checking valid_values is Iterable[str]
def validate_one_of(val: str, valid_values) -> None:
    """Test if object `val` is a member of container `valid_values`.
    Raise a AssertionError if it is not a member. The exception message contains
    both, the representation (__repr__) of `val` as well as the representation
    of all items in `valid_values`.
    """
    if val not in valid_values:
        options_string = ', '.join("'{}'".format(v) for v in valid_values)
        raise AssertionError("Must be one of {}. Got '{}'.".format(options_string, val))


def validate_true_false(val) -> None:
    validate_one_of(val, ['true', 'false'])


def validate_int_in_range(value, low, high):
    try:
        int_value = int(value)
    except ValueError as ex:
        raise AssertionError('Must be an integer but got a {}: {}'.format(type_str(value), value)) from ex

    # Only a lower bound
    if high is None:
        assert low <= int_value, 'Must be above {}'.format(low)
    else:
        assert low <= int_value <= high, 'Must be between {} and {} inclusive'.format(low, high)


def validate_json_list(value):
    try:
        items = json.loads(value)
    except ValueError as ex:
        raise AssertionError("Must be a JSON formatted list, but couldn't be parsed the given "
                             "value `{}` as one because of: {}".format(value, ex)) from ex
    assert isinstance(items, list), "Must be a JSON list. Got a {}".format(type_str(items))

    non_str = list(filter(lambda x: not isinstance(x, str), items))
    assert not non_str, "Items in list must be strings, got invalid values: {}".format(
        ", ".join("{} type {}".format(elem, type_str(elem)) for elem in non_str))
    return items


def validate_ipv4_addresses(ips: list):
    def try_parse_ip(ip):
        try:
            return socket.inet_pton(socket.AF_INET, ip)
        except OSError:
            return None
    invalid_ips = list(filter(lambda ip: try_parse_ip(ip) is None, ips))
    assert not len(invalid_ips), 'Invalid IPv4 addresses in list: {}'.format(', '.join(invalid_ips))


def is_azure_addr(addr: str):
    return addr.startswith('[[[reference(') and addr.endswith(').ipConfigurations[0].properties.privateIPAddress]]]')


def validate_ip_list(json_str: str):
    nodes_list = validate_json_list(json_str)
    check_duplicates(nodes_list)
    # Validate azure addresses which are a bit magical late binding stuff independently of just a
    # list of static IPv4 addresses
    if any(map(is_azure_addr, nodes_list)):
        assert all(map(is_azure_addr, nodes_list)), "Azure static master list and IP based static " \
            "master list cannot be mixed. Use either all Azure IP references or IPv4 addresses."
        return
    validate_ipv4_addresses(nodes_list)


def validate_ip_port_list(json_str: str):
    nodes_list = validate_json_list(json_str)
    check_duplicates(nodes_list)
    # Validate azure addresses which are a bit magical late binding stuff independently of just a
    # list of static IPv4 addresses
    if any(map(is_azure_addr, nodes_list)):
        assert all(map(is_azure_addr, nodes_list)), "Azure resolver list and IP based static " \
            "resolver list cannot be mixed. Use either all Azure IP references or IPv4 addresses."
        return
    # Create a list of only ip addresses by spliting the port from the node. Use the resulting
    # ip_list to validate that it is an ipv4 address. If the port was specified, validate its
    # value is between 1 and 65535.
    ip_list = []
    for node in nodes_list:
        ip, separator, port = node.rpartition(':')
        if not separator:
            ip = node
        else:
            validate_int_in_range(port, 1, 65535)
        ip_list.append(ip)
    validate_ipv4_addresses(ip_list)


def calculate_environment_variable(name):
    value = os.getenv(name)
    assert value is not None, "{} must be a set environment variable".format(name)
    return value


def calulate_dcos_image_commit():
    dcos_image_commit = os.getenv('DCOS_IMAGE_COMMIT', None)

    if dcos_image_commit is None:
        dcos_image_commit = check_output(['git', 'rev-parse', 'HEAD']).decode('utf-8').strip()

    assert dcos_image_commit is not None, "Unable to set dcos_image_commit from teamcity or git."

    return dcos_image_commit


def calculate_resolvers_str(resolvers):
    # Validation because accidentally slicing a string instead of indexing a
    # list of resolvers then finding out at cluster launch is painful.
    resolvers = json.loads(resolvers)
    assert isinstance(resolvers, list)
    return ",".join(resolvers)


def calculate_mesos_dns_resolvers_str(resolvers):
    resolver_list = json.loads(resolvers)

    # Mesos-DNS unfortunately requires completley different config parameters
    # for saying "Don't resolve / reject non-Mesos-DNS requests" than "there are
    # no upstream resolvers". As such, if resolvers is given output that.
    # Otherwise output the option externalOn which means "don't try resolving
    # external queries / just fail fast without an error."
    # This logic _should_ live in the Jinja template but it unfortunately can't
    # because the "unset argument detection" in Jinja doesn't work around using
    # jinja functions (the function names show up as unset arguments...).
    # As such, generate the full JSON line and replace it in the manner given
    # above.
    if len(resolver_list) > 0:
        return '"resolvers": ' + resolvers
    else:
        return '"externalOn": false'


def validate_mesos_log_retention_mb(mesos_log_retention_mb):
    assert int(mesos_log_retention_mb) >= 1024, "Must retain at least 1024 MB of logs"


def calculate_mesos_log_retention_count(mesos_log_retention_mb):
    # Determine how many 256 MB log chunks can be fit into the given size.
    # We assume a 90% compression factor; logs are compressed after 2 rotations.
    # We return the number of times the log can be rotated by logrotate;
    # this is one less than the total number of log file retained.
    return str(int(1 + (int(mesos_log_retention_mb) - 512) / 256 * 10))


def calculate_mesos_log_directory_max_files(mesos_log_retention_mb):
    # We allow some maximum number of temporary/random files in the
    # Mesos log directory.  This maximum takes into account the number
    # of rotated logs that stay in the archive subdirectory.
    return str(25 + int(calculate_mesos_log_retention_count(mesos_log_retention_mb)))


def calculate_ip_detect_contents(ip_detect_filename):
    assert os.path.exists(ip_detect_filename), "ip-detect script `{}` must exist".format(ip_detect_filename)
    return yaml.dump(open(ip_detect_filename, encoding='utf-8').read())


def calculate_ip_detect_public_contents(ip_detect_contents):
    return ip_detect_contents


def calculate_rexray_config_contents(rexray_config):
    return yaml.dump(
        # Assume block style YAML (not flow) for REX-Ray config.
        yaml.dump(json.loads(rexray_config), default_flow_style=False)
    )


def validate_json_dictionary(data):
    # TODO(cmaloney): Pull validate_json() out.
    try:
        loaded = json.loads(data)
        assert isinstance(loaded, dict), "Must be a JSON dictionary. Got a {}".format(type_str(loaded))
        return loaded
    except ValueError as ex:
        raise AssertionError("Must be valid JSON. Got: {}".format(data)) from ex


def calculate_gen_resolvconf_search(dns_search):
    if len(dns_search) > 0:
        return "SEARCH=" + dns_search
    else:
        return ""


def calculate_mesos_hooks(dcos_remove_dockercfg_enable):
    if dcos_remove_dockercfg_enable == 'true':
        return "com_mesosphere_dcos_RemoverHook"
    else:
        return ""


def calculate_use_mesos_hooks(mesos_hooks):
    if mesos_hooks == "":
        return "false"
    else:
        return "true"


def validate_oauth_enabled(oauth_enabled):
    # Should correspond with oauth_enabled in gen/azure/calc.py
    if oauth_enabled in ["[[[variables('oauthEnabled')]]]", '{ "Ref" : "OAuthEnabled" }']:
        return
    validate_true_false(oauth_enabled)


def validate_dcos_overlay_network(dcos_overlay_network):
    try:
        overlay_network = json.loads(dcos_overlay_network)
    except ValueError:
        # TODO(cmaloney): This is not the right form to do this
        assert False, "Provided input was not valid JSON: {}".format(dcos_overlay_network)
    # Check the VTEP IP, VTEP MAC keys are present in the overlay
    # configuration
    assert 'vtep_subnet' in overlay_network.keys(), (
        'Missing "vtep_subnet" in overlay configuration {}'.format(overlay_network))

    try:
        ipaddress.ip_network(overlay_network['vtep_subnet'])
    except ValueError as ex:
        # TODO(cmaloney): This is incorrect currently.
        assert False, (
            "Incorrect value for vtep_subnet. Only IPv4 "
            "values are allowed: {}".format(ex))

    assert 'vtep_mac_oui' in overlay_network.keys(), (
        'Missing "vtep_mac_oui" in overlay configuration {}'.format(overlay_network))

    assert 'overlays' in overlay_network.keys(), (
        'Missing "overlays" in overlay configuration {}'.format(overlay_network))
    assert len(overlay_network['overlays']) > 0, (
        'We need at least one overlay network configuration {}'.format(overlay_network))

    for overlay in overlay_network['overlays']:
        if (len(overlay['name']) > 13):
            assert False, "Overlay name cannot exceed 13 characters:{}".format(overlay['name'])
        try:
            ipaddress.ip_network(overlay['subnet'])
        except ValueError as ex:
            assert False, (
                "Incorrect value for vtep_subnet. Only IPv4 "
                "values are allowed: {}".format(ex))


def calculate_oauth_available(oauth_enabled):
    return oauth_enabled


def validate_num_masters(num_masters):
    assert int(num_masters) in [1, 3, 5, 7, 9], "Must have 1, 3, 5, 7, or 9 masters. Found {}".format(num_masters)


def validate_bootstrap_url(bootstrap_url):
    assert len(bootstrap_url) > 1, "Should be a url (http://example.com/bar or file:///path/to/local/cache)"
    assert bootstrap_url[-1] != '/', "Must not end in a '/'"


def validate_channel_name(channel_name):
    assert len(channel_name) > 1, "Must be more than 2 characters"
    assert channel_name[0] != '/', "Must not start with a '/'"
    assert channel_name[-1] != '/', "Must not end with a '/'"


def validate_dns_search(dns_search):
    assert '\n' not in dns_search, "Newlines are not allowed"
    assert ',' not in dns_search, "Commas are not allowed"

    # resolv.conf requirements
    assert len(dns_search) < 256, "Must be less than 256 characters long"
    assert len(dns_search.split()) <= 6, "Must contain no more than 6 domains"


def validate_master_list(master_list):
    return validate_ip_list(master_list)


def validate_resolvers(resolvers):
    return validate_ip_port_list(resolvers)


def validate_mesos_dns_ip_sources(mesos_dns_ip_sources):
    return validate_json_list(mesos_dns_ip_sources)


def calc_num_masters(master_list):
    return str(len(json.loads(master_list)))


def calculate_config_id(dcos_image_commit, user_arguments, template_filenames):
    return hash_checkout({
        "commit": dcos_image_commit,
        "user_arguments": json.loads(user_arguments),
        "template_filenames": json.loads(template_filenames)})


def calculate_cluster_packages(package_names, config_id):
    def get_package_id(package_name):
        pkg_id_str = "{}--setup_{}".format(package_name, config_id)
        # validate the pkg_id_str generated is a valid PackageId
        return pkg_id_str

    cluster_package_ids = list(sorted(map(get_package_id, json.loads(package_names))))
    return json.dumps(cluster_package_ids)


def validate_cluster_packages(cluster_packages):
    pkg_id_list = json.loads(cluster_packages)
    for pkg_id in pkg_id_list:
        try:
            PackageId(pkg_id)
        except pkgpanda.exceptions.ValidationError as ex:
            raise AssertionError(str(ex)) from ex


def calculate_no_proxy(no_proxy):
    user_proxy_config = validate_json_list(no_proxy)
    return ",".join(['*.mesos,127.0.0.1,localhost'] + user_proxy_config)


def validate_zk_hosts(exhibitor_zk_hosts):
    # TODO(malnick) Add validation of IPv4 address and port to this
    assert not exhibitor_zk_hosts.startswith('zk://'), "Must be of the form `host:port,host:port', not start with zk://"


def validate_zk_path(exhibitor_zk_path):
    assert exhibitor_zk_path.startswith('/'), "Must be of the form /path/to/znode"


def calculate_exhibitor_static_ensemble(master_list):
    masters = json.loads(master_list)
    masters.sort()
    return ','.join(['%d:%s' % (i + 1, m) for i, m in enumerate(masters)])


def calculate_adminrouter_auth_enabled(oauth_enabled):
    return oauth_enabled


def calculate_config_yaml(user_arguments):
    return textwrap.indent(
        yaml.dump(json.loads(user_arguments), default_style='|', default_flow_style=False, indent=2),
        prefix='  ' * 3)


def validate_os_type(os_type):
    validate_one_of(os_type, ['coreos', 'el7'])


def validate_bootstrap_tmp_dir(bootstrap_tmp_dir):
    # Must be non_empty
    assert bootstrap_tmp_dir, "Must not be empty"

    # Should not start or end with `/`
    assert bootstrap_tmp_dir[0] != '/' and bootstrap_tmp_dir[-1] != 0, \
        "Must be an absolute path to a directory, although leave off the `/` at the beginning and end."


def calculate_minuteman_min_named_ip_erltuple(minuteman_min_named_ip):
    return ip_to_erltuple(minuteman_min_named_ip)


def calculate_minuteman_max_named_ip_erltuple(minuteman_max_named_ip):
    return ip_to_erltuple(minuteman_max_named_ip)


def ip_to_erltuple(ip):
    return '{' + ip.replace('.', ',') + '}'


def validate_minuteman_min_named_ip(minuteman_min_named_ip):
    validate_ipv4_addresses([minuteman_min_named_ip])


def validate_minuteman_max_named_ip(minuteman_max_named_ip):
    validate_ipv4_addresses([minuteman_max_named_ip])


def calculate_docker_credentials_dcos_owned(cluster_docker_credentials):
    if cluster_docker_credentials == "{}":
        return "false"
    else:
        return "true"


def calculate_cluster_docker_credentials_path(cluster_docker_credentials_dcos_owned):
    return {
        'true': '/opt/mesosphere/etc/docker_credentials',
        'false': '/etc/mesosphere/docker_credentials'
    }[cluster_docker_credentials_dcos_owned]


def calculate_cluster_docker_registry_enabled(cluster_docker_registry_url):
    return 'false' if cluster_docker_registry_url == '' else 'true'


__logrotate_slave_module_name = 'org_apache_mesos_LogrotateContainerLogger'


entry = {
    'validate': [
        validate_num_masters,
        validate_bootstrap_url,
        validate_channel_name,
        validate_dns_search,
        validate_master_list,
        validate_resolvers,
        validate_zk_hosts,
        validate_zk_path,
        validate_cluster_packages,
        validate_oauth_enabled,
        validate_mesos_dns_ip_sources,
        validate_mesos_log_retention_mb,
        lambda telemetry_enabled: validate_true_false(telemetry_enabled),
        lambda master_dns_bindall: validate_true_false(master_dns_bindall),
        validate_os_type,
        validate_dcos_overlay_network,
        lambda dcos_overlay_enable: validate_true_false(dcos_overlay_enable),
        lambda dcos_overlay_mtu: validate_int_in_range(dcos_overlay_mtu, 552, None),
        lambda dcos_overlay_config_attempts: validate_int_in_range(dcos_overlay_config_attempts, 0, 10),
        lambda dcos_remove_dockercfg_enable: validate_true_false(dcos_remove_dockercfg_enable),
        lambda rexray_config: validate_json_dictionary(rexray_config),
        lambda check_time: validate_true_false(check_time),
        validate_minuteman_min_named_ip,
        validate_minuteman_max_named_ip,
        lambda cluster_docker_credentials_dcos_owned: validate_true_false(cluster_docker_credentials_dcos_owned),
        lambda cluster_docker_credentials_enabled: validate_true_false(cluster_docker_credentials_enabled),
        lambda cluster_docker_credentials_write_to_etc: validate_true_false(cluster_docker_credentials_write_to_etc),
        lambda cluster_docker_credentials: validate_json_dictionary(cluster_docker_credentials),
        lambda aws_masters_have_public_ip: validate_true_false(aws_masters_have_public_ip)
    ],
    'default': {
        'bootstrap_tmp_dir': 'tmp',
        'bootstrap_variant': lambda: calculate_environment_variable('BOOTSTRAP_VARIANT'),
        'use_proxy': 'false',
        'weights': '',
        'adminrouter_auth_enabled': calculate_adminrouter_auth_enabled,
        'oauth_enabled': 'true',
        'oauth_available': calculate_oauth_available,
        'telemetry_enabled': 'true',
        'check_time': 'true',
        'docker_remove_delay': '1hrs',
        'docker_stop_timeout': '20secs',
        'gc_delay': '2days',
        'ip_detect_contents': calculate_ip_detect_contents,
        'ip_detect_public_contents': calculate_ip_detect_public_contents,
        'dns_search': '',
        'auth_cookie_secure_flag': 'false',
        'master_dns_bindall': 'true',
        'mesos_dns_ip_sources': '["host", "netinfo"]',
        'mesos_container_logger': __logrotate_slave_module_name,
        'mesos_log_retention_mb': '4000',
        'oauth_issuer_url': 'https://dcos.auth0.com/',
        'oauth_client_id': '3yF5TOSzdlI45Q1xspxzeoGBe9fNxm9m',
        'oauth_auth_redirector': 'https://auth.dcos.io',
        'oauth_auth_host': 'https://dcos.auth0.com',
        'ui_tracking': 'true',
        'ui_banner': 'false',
        'ui_banner_background_color': '#1E232F',
        'ui_banner_foreground_color': '#FFFFFF',
        'ui_banner_header_title': 'null',
        'ui_banner_header_content': 'null',
        'ui_banner_footer_content': 'null',
        'ui_banner_image_path': 'null',
        'ui_banner_dismissible': 'null',
        'dcos_overlay_config_attempts': '4',
        'dcos_overlay_mtu': '1420',
        'dcos_overlay_enable': "true",
        'dcos_overlay_network': json.dumps({
            'vtep_subnet': '44.128.0.0/20',
            'vtep_mac_oui': '70:B3:D5:00:00:00',
            'overlays': [{
                'name': 'dcos',
                'subnet': '9.0.0.0/8',
                'prefix': 24
            }]
        }),
        'dcos_remove_dockercfg_enable': "false",
        'minuteman_min_named_ip': '11.0.0.0',
        'minuteman_max_named_ip': '11.255.255.255',
        'no_proxy': '',
        'rexray_config_preset': '',
        'rexray_config': json.dumps({
            # Disabled. REX-Ray will start but not register as a volume driver.
            'rexray': {
                'loglevel': 'info',
                'modules': {
                    'default-admin': {
                        'host': 'tcp://127.0.0.1:61003'
                    },
                    'default-docker': {
                        'disabled': True
                    }
                }
            }
        }),
        'cluster_docker_registry_url': '',
        'cluster_docker_credentials_dcos_owned': calculate_docker_credentials_dcos_owned,
        'cluster_docker_credentials_write_to_etc': 'false',
        'cluster_docker_credentials_enabled': 'false',
        'cluster_docker_credentials': "{}"
    },
    'must': {
        'custom_auth': 'false',
        'master_quorum': lambda num_masters: str(floor(int(num_masters) / 2) + 1),
        'resolvers_str': calculate_resolvers_str,
        'dcos_image_commit': calulate_dcos_image_commit,
        'mesos_dns_resolvers_str': calculate_mesos_dns_resolvers_str,
        'mesos_log_retention_count': calculate_mesos_log_retention_count,
        'mesos_log_directory_max_files': calculate_mesos_log_directory_max_files,
        'dcos_version': '1.8.5',
        'dcos_gen_resolvconf_search_str': calculate_gen_resolvconf_search,
        'curly_pound': '{#',
        'cluster_packages': calculate_cluster_packages,
        'config_id': calculate_config_id,
        'exhibitor_static_ensemble': calculate_exhibitor_static_ensemble,
        'ui_branding': 'false',
        'ui_external_links': 'false',
        'ui_networking': 'false',
        'ui_organization': 'false',
        'minuteman_forward_metrics': 'false',
        'minuteman_min_named_ip_erltuple': calculate_minuteman_min_named_ip_erltuple,
        'minuteman_max_named_ip_erltuple': calculate_minuteman_max_named_ip_erltuple,
        'mesos_isolation': 'cgroups/cpu,cgroups/mem,disk/du,network/cni,filesystem/linux,docker/runtime,docker/volume',
        'config_yaml': calculate_config_yaml,
        'mesos_hooks': calculate_mesos_hooks,
        'use_mesos_hooks': calculate_use_mesos_hooks,
        'rexray_config_contents': calculate_rexray_config_contents,
        'no_proxy_final': calculate_no_proxy,
        'cluster_docker_credentials_path': calculate_cluster_docker_credentials_path,
        'cluster_docker_registry_enabled': calculate_cluster_docker_registry_enabled,
    },
    'conditional': {
        'master_discovery': {
            'master_http_loadbalancer': {},
            'static': {
                'must': {'num_masters': calc_num_masters}
            }
        },
        'provider': {
            'onprem': {
                'default': {
                    'resolvers': '["8.8.8.8", "8.8.4.4"]',
                    'ip_detect_filename': 'genconf/ip-detect',
                    'bootstrap_id': lambda: calculate_environment_variable('BOOTSTRAP_ID')
                },
            },
            'azure': gen.azure.calc.entry,
            'aws': gen.aws.calc.entry,
            'other': {}
        },
        'rexray_config_preset': {
            '': {},
            'aws': {
                'must': {
                    'rexray_config': json.dumps({
                        # Use IAM Instance Profile for auth.
                        'rexray': {
                            'loglevel': 'info',
                            'modules': {
                                'default-admin': {
                                    'host': 'tcp://127.0.0.1:61003'
                                }
                            },
                            'storageDrivers': ['ec2'],
                            'volume': {
                                'unmount': {
                                    'ignoreusedcount': True
                                }
                            }
                        }
                    })
                }
            }
        }
    }
}
