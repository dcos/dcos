""" This module contains the logic for specifying and validating the top-level
DC/OS configuration from user arguments

The data structure called 'entry' is what defines which validation checks
should be run, how arguments should be calculated, which arguments should have
set defaults, which arguments should be user specified, and how some arguments
should be calculated.

HOW THIS WORKS:
    The ARGUMENT NAME in the validate and calculate functions correspond
    to the FIELD FROM THE INPUT (config.yaml).

Notes:
validate_* function: the arguments it takes will define the arguments which the
    function is evaluated against. All validations are performed at once

argument calculation functions: like validation function, the arguments specified
    will be pulled from the Source or user arguments. These function can be used
    for both 'default' and 'must'


See gen.internals for more on how the nuts and bolts of this process works
"""
import collections
import ipaddress
import json
import os
import socket
import string
import textwrap
from math import floor
from subprocess import check_output
from urllib.parse import urlparse

import schema
import yaml

import gen.internals
import pkgpanda.exceptions
from pkgpanda import PackageId
from pkgpanda.util import hash_checkout


def type_str(value):
    return type(value).__name__


def check_duplicates(items: list):
    counter = collections.Counter(items)
    duplicates = dict(filter(lambda x: x[1] > 1, counter.items()))
    assert not duplicates, 'List cannot contain duplicates: {}'.format(
        ', '.join('{} appears {} times'.format(*item) for item in duplicates.items()))


def validate_true_false(val) -> None:
    gen.internals.validate_one_of(val, ['true', 'false'])


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


def valid_ipv4_address(ip):
    try:
        socket.inet_pton(socket.AF_INET, ip)
        return True
    except OSError:
        return False
    except TypeError:
        return False


def validate_ipv4_addresses(ips: list):
    invalid_ips = []
    for ip in ips:
        if not valid_ipv4_address(ip):
            invalid_ips.append(ip)
    assert not invalid_ips, 'Invalid IPv4 addresses in list: {}'.format(', '.join(invalid_ips))


def validate_url(url: str):
    try:
        urlparse(url)
    except ValueError as ex:
        raise AssertionError(
            "Couldn't parse given value `{}` as an URL".format(url)
        ) from ex


def validate_ip_list(json_str: str):
    nodes_list = validate_json_list(json_str)
    check_duplicates(nodes_list)
    validate_ipv4_addresses(nodes_list)


def validate_ip_port_list(json_str: str):
    nodes_list = validate_json_list(json_str)
    check_duplicates(nodes_list)
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


def validate_mesos_container_log_sink(mesos_container_log_sink):
    assert mesos_container_log_sink in ['journald', 'logrotate', 'journald+logrotate'], \
        "Container logs must go to 'journald', 'logrotate', or 'journald+logrotate'."


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


def calculate_ip_detect_public_contents(ip_detect_contents, ip_detect_public_filename):
    if ip_detect_public_filename != '':
        return calculate_ip_detect_contents(ip_detect_public_filename)
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


def validate_network_default_name(dcos_overlay_network_default_name, dcos_overlay_network):
    try:
        overlay_network = json.loads(dcos_overlay_network)
    except ValueError as ex:
        raise AssertionError("Provided input was not valid JSON: {}".format(dcos_overlay_network)) from ex

    overlay_names = map(lambda overlay: overlay['name'], overlay_network['overlays'])

    assert dcos_overlay_network_default_name in overlay_names, (
        "Default overlay network name does not reference a defined overlay network: {}".format(
            dcos_overlay_network_default_name))


def validate_dcos_ucr_default_bridge_subnet(dcos_ucr_default_bridge_subnet):
    try:
        ipaddress.ip_network(dcos_ucr_default_bridge_subnet)
    except ValueError as ex:
        raise AssertionError(
            "Incorrect value for dcos_ucr_default_bridge_subnet: {}."
            " Only IPv4 subnets are allowed".format(dcos_ucr_default_bridge_subnet)) from ex


def validate_dcos_overlay_network(dcos_overlay_network):
    try:
        overlay_network = json.loads(dcos_overlay_network)
    except ValueError as ex:
        raise AssertionError("Provided input was not valid JSON: {}".format(dcos_overlay_network)) from ex

    # Check the VTEP IP, VTEP MAC keys are present in the overlay
    # configuration
    assert 'vtep_subnet' in overlay_network.keys(), (
        'Missing "vtep_subnet" in overlay configuration {}'.format(overlay_network))

    try:
        ipaddress.ip_network(overlay_network['vtep_subnet'])
    except ValueError as ex:
        raise AssertionError(
            "Incorrect value for vtep_subnet: {}."
            " Only IPv4 values are allowed".format(overlay_network['vtep_subnet'])) from ex

    assert 'vtep_mac_oui' in overlay_network.keys(), (
        'Missing "vtep_mac_oui" in overlay configuration {}'.format(overlay_network))

    assert 'overlays' in overlay_network.keys(), (
        'Missing "overlays" in overlay configuration {}'.format(overlay_network))
    assert len(overlay_network['overlays']) > 0, (
        'We need at least one overlay network configuration {}'.format(overlay_network))

    for overlay in overlay_network['overlays']:
        assert (len(overlay['name']) <= 13), (
            "Overlay name cannot exceed 13 characters:{}".format(overlay['name']))
        try:
            ipaddress.ip_network(overlay['subnet'])
        except ValueError as ex:
            raise AssertionError(
                "Incorrect value for vtep_subnet {}."
                " Only IPv4 values are allowed".format(overlay['subnet'])) from ex


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


def calculate_config_id(dcos_image_commit, template_filenames, sources_id):
    return hash_checkout({
        "commit": dcos_image_commit,
        "template_filenames": json.loads(template_filenames),
        "sources_id": sources_id})


def calculate_config_package_ids(config_package_names, config_id):
    def get_config_package_id(config_package_name):
        pkg_id_str = "{}--setup_{}".format(config_package_name, config_id)
        # validate the pkg_id_str generated is a valid PackageId
        return pkg_id_str

    return json.dumps(list(sorted(map(get_config_package_id, json.loads(config_package_names)))))


def calculate_cluster_packages(config_package_ids, package_ids):
    return json.dumps(sorted(json.loads(config_package_ids) + json.loads(package_ids)))


def validate_cluster_packages(cluster_packages):
    pkg_id_list = json.loads(cluster_packages)
    for pkg_id in pkg_id_list:
        try:
            PackageId(pkg_id)
        except pkgpanda.exceptions.ValidationError as ex:
            raise AssertionError(str(ex)) from ex


def calculate_no_proxy(no_proxy):
    user_proxy_config = validate_json_list(no_proxy)
    return ",".join(['.mesos,.thisdcos.directory,.dcos.directory,.zk,127.0.0.1,localhost'] + user_proxy_config)


def validate_zk_hosts(exhibitor_zk_hosts):
    # TODO(malnick) Add validation of IPv4 address and port to this
    assert not exhibitor_zk_hosts.startswith('zk://'), "Must be of the form `host:port,host:port', not start with zk://"


def validate_zk_path(exhibitor_zk_path):
    assert exhibitor_zk_path.startswith('/'), "Must be of the form /path/to/znode"


def calculate_exhibitor_static_ensemble(master_list):
    masters = json.loads(master_list)
    masters.sort()
    return ','.join(['%d:%s' % (i + 1, m) for i, m in enumerate(masters)])


def calculate_exhibitor_admin_password_enabled(exhibitor_admin_password):
    if exhibitor_admin_password:
        return 'true'
    return 'false'


def calculate_adminrouter_auth_enabled(oauth_enabled):
    return oauth_enabled


def calculate_config_yaml(user_arguments):
    return textwrap.indent(
        yaml.dump(json.loads(user_arguments), default_style='|', default_flow_style=False, indent=2),
        prefix='  ' * 3)


def calculate_mesos_isolation(enable_gpu_isolation):
    isolators = ('cgroups/cpu,cgroups/mem,disk/du,network/cni,filesystem/linux,'
                 'docker/runtime,docker/volume,volume/sandbox_path,volume/secret,posix/rlimits,'
                 'namespaces/pid,linux/capabilities,com_mesosphere_MetricsIsolatorModule')
    if enable_gpu_isolation == 'true':
        isolators += ',cgroups/devices,gpu/nvidia'
    return isolators


def validate_os_type(os_type):
    gen.internals.validate_one_of(os_type, ['coreos', 'el7'])


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


def validate_cosmos_config(cosmos_config):
    """The schema for this configuration is.
    {
      "schema": "http://json-schema.org/draft-04/schema#",
      "type": "object",
      "properties": {
        "staged_package_storage_uri": {
          "type": "string"
        },
        "package_storage_uri": {
          "type": "string"
        }
      }
    }
    """

    config = validate_json_dictionary(cosmos_config)
    expects = ['staged_package_storage_uri', 'package_storage_uri']
    found = list(filter(lambda value: value in config, expects))

    if len(found) == 0:
        # User didn't specify any configuration; nothing to do
        pass
    elif len(found) == 1:
        # User specified one parameter but not the other; fail
        raise AssertionError(
            'cosmos_config must be a dictionary containing both {}, or must '
            'be left empty. Found only {}'.format(' '.join(expects), found)
        )
    else:
        # User specified both parameters; make sure they are URLs
        for value in found:
            validate_url(config[value])


def calculate_cosmos_staged_package_storage_uri_flag(cosmos_config):
    config = validate_json_dictionary(cosmos_config)
    if 'staged_package_storage_uri' in config:
        return (
            '-com.mesosphere.cosmos.stagedPackageStorageUri={}'.format(
                config['staged_package_storage_uri']
            )
        )
    else:
        return ''


def calculate_cosmos_package_storage_uri_flag(cosmos_config):
    config = validate_json_dictionary(cosmos_config)
    if 'package_storage_uri' in config:
        return (
            '-com.mesosphere.cosmos.packageStorageUri={}'.format(
                config['package_storage_uri']
            )
        )
    else:
        return ''


def calculate_profile_symlink_target_dir(profile_symlink_target):
    return os.path.dirname(profile_symlink_target)


def calculate_set(parameter):
    if parameter == '':
        return 'false'
    else:
        return 'true'


def validate_exhibitor_storage_master_discovery(master_discovery, exhibitor_storage_backend):
    if master_discovery != 'static':
        assert exhibitor_storage_backend != 'static', "When master_discovery is not static, " \
            "exhibitor_storage_backend must be non-static. Having a variable list of master which " \
            "are discovered by agents using the master_discovery method but also having a fixed " \
            "known at install time static list of master ips doesn't " \
            "`master_http_load_balancer` then exhibitor_storage_backend must not be static."


def validate_s3_prefix(s3_prefix):
    # See DCOS_OSS-1353
    assert not s3_prefix.endswith('/'), "Must be a file path and cannot end in a /"


def validate_dns_bind_ip_blacklist(dns_bind_ip_blacklist):
    return validate_ip_list(dns_bind_ip_blacklist)


def validate_dns_forward_zones(dns_forward_zones):
    """
     "forward_zones": [["a.contoso.com", [["1.1.1.1", 53],
                                          ["2.2.2.2", 53]]],
                       ["b.contoso.com", [["3.3.3.3", 53],
                                          ["4.4.4.4", 53]]]]
    """

    def fz_err(msg):
        return 'Invalid "dns_forward_zones": {}'.format(msg)

    zone_defs = None
    try:
        zone_defs = json.loads(dns_forward_zones)
    except ValueError as ex:
        raise AssertionError(fz_err("{} is not valid JSON: {}".format(dns_forward_zones, ex))) from ex
    assert isinstance(zone_defs, list), fz_err("{} is not a list".format(zone_defs))

    for z in zone_defs:
        assert isinstance(z, list), fz_err("{} is not a list".format(z))
        assert len(z) == 2, fz_err("{} is not length 2".format(z))
        assert isinstance(z[0], str), fz_err("{} is not a string".format(z))

        upstreams = z[1]
        for u in upstreams:
            assert isinstance(u, list), fz_err("{} not a list".format(u))
            assert len(u) == 2, fz_err("{} not length 2".format(u))

            ip = u[0]
            port = u[1]
            assert valid_ipv4_address(ip), fz_err("{} not a valid IP address".format(ip))
            validate_int_in_range(port, 1, 65535)


def calculate_fair_sharing_excluded_resource_names(gpus_are_scarce):
    if gpus_are_scarce == 'true':
        return 'gpus'
    return ''


def calculate_has_mesos_max_completed_tasks_per_framework(mesos_max_completed_tasks_per_framework):
    return calculate_set(mesos_max_completed_tasks_per_framework)


def validate_mesos_max_completed_tasks_per_framework(
        mesos_max_completed_tasks_per_framework, has_mesos_max_completed_tasks_per_framework):
    if has_mesos_max_completed_tasks_per_framework == 'true':
        try:
            int(mesos_max_completed_tasks_per_framework)
        except ValueError as ex:
            raise AssertionError("Error parsing 'mesos_max_completed_tasks_per_framework' "
                                 "parameter as an integer: {}".format(ex)) from ex


def calculate_check_config_contents(check_config, custom_checks, check_search_path, check_ld_library_path):

    def merged_check_config(config_a, config_b):
        # config_b overwrites config_a. Validation should assert that names won't conflict.

        def cluster_checks(config):
            return config.get('cluster_checks', {})

        def node_checks_section(config):
            return config.get('node_checks', {})

        def node_checks(config):
            return node_checks_section(config).get('checks', {})

        def prestart_node_checks(config):
            return node_checks_section(config).get('prestart', [])

        def poststart_node_checks(config):
            return node_checks_section(config).get('poststart', [])

        def merged_dict(dict_a, dict_b):
            merged = dict_a.copy()
            merged.update(dict_b)
            return merged

        merged_cluster_checks = merged_dict(cluster_checks(config_a), cluster_checks(config_b))
        merged_node_checks = {
            'checks': merged_dict(node_checks(config_a), node_checks(config_b)),
            'prestart': prestart_node_checks(config_a) + prestart_node_checks(config_b),
            'poststart': poststart_node_checks(config_a) + poststart_node_checks(config_b),
        }

        merged_config = {}
        if merged_cluster_checks:
            merged_config['cluster_checks'] = merged_cluster_checks
        if merged_node_checks['checks']:
            merged_config['node_checks'] = merged_node_checks
        return merged_config

    dcos_checks = json.loads(check_config)
    user_checks = json.loads(custom_checks)
    merged_checks = merged_check_config(user_checks, dcos_checks)
    merged_checks['check_env'] = {
        'PATH': check_search_path,
        'LD_LIBRARY_PATH': check_ld_library_path,
    }
    return yaml.dump(json.dumps(merged_checks, indent=2))


def calculate_check_config(check_time):
    check_config = {
        'node_checks': {
            'checks': {
                'components_master': {
                    'description': 'All DC/OS components are healthy.',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', '--role', 'master', 'components'],
                    'timeout': '3s',
                    'roles': ['master']
                },
                'components_agent': {
                    'description': 'All DC/OS components are healthy',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', '--role', 'agent', 'components', '--port', '61001'],
                    'timeout': '3s',
                    'roles': ['agent']
                },
                'xz': {
                    'description': 'The xz utility is available',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', 'executable', 'xz'],
                    'timeout': '1s'
                },
                'tar': {
                    'description': 'The tar utility is available',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', 'executable', 'tar'],
                    'timeout': '1s'
                },
                'curl': {
                    'description': 'The curl utility is available',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', 'executable', 'curl'],
                    'timeout': '1s'
                },
                'unzip': {
                    'description': 'The unzip utility is available',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', 'executable', 'unzip'],
                    'timeout': '1s'
                },
                'ip_detect_script': {
                    'description': 'The IP detect script produces valid output',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', 'ip'],
                    'timeout': '1s'
                },
                'mesos_master_replog_synchronized': {
                    'description': 'The Mesos master has synchronized its replicated log',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', '--role', 'master', 'mesos-metrics'],
                    'timeout': '1s',
                    'roles': ['master']
                },
                'mesos_agent_registered_with_masters': {
                    'description': 'The Mesos agent has registered with the masters',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', '--role', 'agent', 'mesos-metrics'],
                    'timeout': '1s',
                    'roles': ['agent']
                },
                'journald_dir_permissions': {
                    'description': 'Journald directory has the right owners and permissions',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', 'journald'],
                    'timeout': '1s',
                },
            },
            'prestart': [],
            'poststart': [
                'components_master',
                'components_agent',
                'xz',
                'tar',
                'curl',
                'unzip',
                'ip_detect_script',
                'mesos_master_replog_synchronized',
                'mesos_agent_registered_with_masters',
                'journald_dir_permissions',
            ],
        },
    }

    if check_time == 'true':
        # Add the clock sync check.
        clock_sync_check_name = 'clock_sync'
        check_config['node_checks']['checks'][clock_sync_check_name] = {
            'description': 'System clock is in sync.',
            'cmd': ['/opt/mesosphere/bin/dcos-checks', 'time'],
            'timeout': '1s'
        }
        check_config['node_checks']['poststart'].append(clock_sync_check_name)

    return json.dumps(check_config)


def validate_check_config(check_config):

    class PrettyReprAnd(schema.And):

        def __repr__(self):
            return self._error

    check_name = PrettyReprAnd(
        str,
        lambda val: len(val) > 0,
        lambda val: not any(w in val for w in string.whitespace),
        error='Check name must be a nonzero length string with no whitespace')

    timeout_units = ['ns', 'us', 'µs', 'ms', 's', 'm', 'h']
    timeout = schema.Regex(
        '^\d+(\.\d+)?({})$'.format('|'.join(timeout_units)),
        error='Timeout must be a string containing an integer or float followed by a unit: {}'.format(
            ', '.join(timeout_units)))

    check_config_schema = schema.Schema({
        schema.Optional('cluster_checks'): {
            check_name: {
                'description': str,
                'cmd': [str],
                'timeout': timeout,
            },
        },
        schema.Optional('node_checks'): {
            'checks': {
                check_name: {
                    'description': str,
                    'cmd': [str],
                    'timeout': timeout,
                    schema.Optional('roles'): schema.Schema(
                        ['master', 'agent'],
                        error='roles must be a list containing master or agent or both',
                    ),
                },
            },
            schema.Optional('prestart'): [check_name],
            schema.Optional('poststart'): [check_name],
        },
    })

    check_config_obj = validate_json_dictionary(check_config)
    try:
        check_config_schema.validate(check_config_obj)
    except schema.SchemaError as exc:
        raise AssertionError(str(exc).replace('\n', ' ')) from exc

    if 'node_checks' in check_config_obj.keys():
        node_checks = check_config_obj['node_checks']
        assert any(k in node_checks.keys() for k in ['prestart', 'poststart']), (
            'At least one of prestart or poststart must be defined in node_checks')
        assert node_checks['checks'].keys() == set(
            node_checks.get('prestart', []) + node_checks.get('poststart', [])), (
            'All node checks must be referenced in either prestart or poststart, or both')

    return check_config_obj


def validate_custom_checks(custom_checks, check_config):

    def cluster_check_names(config):
        return set(config.get('cluster_checks', {}).keys())

    def node_check_names(config):
        return set(config.get('node_checks', {}).get('checks', {}).keys())

    user_checks = json.loads(custom_checks)
    dcos_checks = json.loads(check_config)
    shared_cluster_check_names = cluster_check_names(user_checks).intersection(cluster_check_names(dcos_checks))
    shared_node_check_names = node_check_names(user_checks).intersection(node_check_names(dcos_checks))

    if shared_cluster_check_names or shared_node_check_names:
        msg = 'Custom check names conflict with builtin checks.'
        if shared_cluster_check_names:
            msg += ' Reserved cluster check names: {}.'.format(', '.join(sorted(shared_cluster_check_names)))
        if shared_node_check_names:
            msg += ' Reserved node check names: {}.'.format(', '.join(sorted(shared_node_check_names)))
        raise AssertionError(msg)


__dcos_overlay_network_default_name = 'dcos'


entry = {
    'validate': [
        validate_s3_prefix,
        validate_num_masters,
        validate_bootstrap_url,
        validate_channel_name,
        validate_dns_search,
        validate_master_list,
        validate_resolvers,
        validate_dns_bind_ip_blacklist,
        validate_dns_forward_zones,
        validate_zk_hosts,
        validate_zk_path,
        validate_cluster_packages,
        lambda oauth_enabled: validate_true_false(oauth_enabled),
        lambda oauth_available: validate_true_false(oauth_available),
        validate_mesos_dns_ip_sources,
        lambda mesos_dns_set_truncate_bit: validate_true_false(mesos_dns_set_truncate_bit),
        validate_mesos_log_retention_mb,
        lambda telemetry_enabled: validate_true_false(telemetry_enabled),
        lambda master_dns_bindall: validate_true_false(master_dns_bindall),
        validate_os_type,
        validate_dcos_overlay_network,
        validate_dcos_ucr_default_bridge_subnet,
        lambda dcos_overlay_network_default_name, dcos_overlay_network:
            validate_network_default_name(dcos_overlay_network_default_name, dcos_overlay_network),
        lambda dcos_overlay_enable: validate_true_false(dcos_overlay_enable),
        lambda dcos_overlay_mtu: validate_int_in_range(dcos_overlay_mtu, 552, None),
        lambda dcos_overlay_config_attempts: validate_int_in_range(dcos_overlay_config_attempts, 0, 10),
        lambda dcos_remove_dockercfg_enable: validate_true_false(dcos_remove_dockercfg_enable),
        lambda rexray_config: validate_json_dictionary(rexray_config),
        lambda check_time: validate_true_false(check_time),
        lambda enable_gpu_isolation: validate_true_false(enable_gpu_isolation),
        validate_minuteman_min_named_ip,
        validate_minuteman_max_named_ip,
        lambda cluster_docker_credentials_dcos_owned: validate_true_false(cluster_docker_credentials_dcos_owned),
        lambda cluster_docker_credentials_enabled: validate_true_false(cluster_docker_credentials_enabled),
        lambda cluster_docker_credentials_write_to_etc: validate_true_false(cluster_docker_credentials_write_to_etc),
        lambda cluster_docker_credentials: validate_json_dictionary(cluster_docker_credentials),
        lambda aws_masters_have_public_ip: validate_true_false(aws_masters_have_public_ip),
        validate_exhibitor_storage_master_discovery,
        lambda exhibitor_admin_password_enabled: validate_true_false(exhibitor_admin_password_enabled),
        validate_cosmos_config,
        lambda enable_lb: validate_true_false(enable_lb),
        lambda adminrouter_tls_1_0_enabled: validate_true_false(adminrouter_tls_1_0_enabled),
        lambda gpus_are_scarce: validate_true_false(gpus_are_scarce),
        validate_mesos_max_completed_tasks_per_framework,
        lambda check_config: validate_check_config(check_config),
        lambda custom_checks: validate_check_config(custom_checks),
        lambda custom_checks, check_config: validate_custom_checks(custom_checks, check_config),
        lambda fault_domain_enabled: validate_true_false(fault_domain_enabled)
    ],
    'default': {
        'bootstrap_tmp_dir': 'tmp',
        'bootstrap_variant': lambda: calculate_environment_variable('BOOTSTRAP_VARIANT'),
        'dns_bind_ip_blacklist': '[]',
        'dns_forward_zones': '[]',
        'use_proxy': 'false',
        'weights': '',
        'adminrouter_auth_enabled': calculate_adminrouter_auth_enabled,
        'adminrouter_tls_1_0_enabled': 'false',
        'oauth_enabled': 'true',
        'oauth_available': 'true',
        'telemetry_enabled': 'true',
        'check_time': 'true',
        'cluster_packages_json': lambda cluster_packages: cluster_packages,
        'enable_lb': 'true',
        'docker_remove_delay': '1hrs',
        'docker_stop_timeout': '20secs',
        'gc_delay': '2days',
        'ip_detect_contents': calculate_ip_detect_contents,
        'ip_detect_public_filename': '',
        'ip_detect_public_contents': calculate_ip_detect_public_contents,
        'dns_search': '',
        'auth_cookie_secure_flag': 'false',
        'master_dns_bindall': 'true',
        'mesos_dns_ip_sources': '["host", "netinfo"]',
        'mesos_dns_set_truncate_bit': 'true',
        'master_external_loadbalancer': '',
        'mesos_log_retention_mb': '4000',
        'mesos_container_log_sink': 'logrotate',
        'mesos_max_completed_tasks_per_framework': '',
        'oauth_issuer_url': 'https://dcos.auth0.com/',
        'oauth_client_id': '3yF5TOSzdlI45Q1xspxzeoGBe9fNxm9m',
        'oauth_auth_redirector': 'https://auth.dcos.io',
        'oauth_auth_host': 'https://dcos.auth0.com',
        'exhibitor_admin_password': '',
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
                'name': __dcos_overlay_network_default_name,
                'subnet': '9.0.0.0/8',
                'prefix': 24
            }]
        }),
        'dcos_overlay_network_default_name': __dcos_overlay_network_default_name,
        'dcos_ucr_default_bridge_subnet': '172.31.254.0/24',
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
                    'default-docker': {
                        'disabled': True
                    }
                },
                'service': 'vfs'
            }
        }),
        'enable_gpu_isolation': 'true',
        'cluster_docker_registry_url': '',
        'cluster_docker_credentials_dcos_owned': calculate_docker_credentials_dcos_owned,
        'cluster_docker_credentials_write_to_etc': 'false',
        'cluster_docker_credentials_enabled': 'false',
        'cluster_docker_credentials': "{}",
        'cosmos_config': '{}',
        'gpus_are_scarce': 'true',
        'check_config': calculate_check_config,
        'custom_checks': '{}',
        'fault_domain_enabled': 'false'
    },
    'must': {
        'custom_auth': 'false',
        'master_quorum': lambda num_masters: str(floor(int(num_masters) / 2) + 1),
        'resolvers_str': calculate_resolvers_str,
        'dcos_image_commit': calulate_dcos_image_commit,
        'mesos_dns_resolvers_str': calculate_mesos_dns_resolvers_str,
        'mesos_log_retention_count': calculate_mesos_log_retention_count,
        'mesos_log_directory_max_files': calculate_mesos_log_directory_max_files,
        'dcos_version': '1.10.0-beta2',
        'dcos_gen_resolvconf_search_str': calculate_gen_resolvconf_search,
        'curly_pound': '{#',
        'config_package_ids': calculate_config_package_ids,
        'cluster_packages': calculate_cluster_packages,
        'config_id': calculate_config_id,
        'exhibitor_static_ensemble': calculate_exhibitor_static_ensemble,
        'exhibitor_admin_password_enabled': calculate_exhibitor_admin_password_enabled,
        'ui_branding': 'false',
        'ui_external_links': 'false',
        'ui_networking': 'false',
        'ui_organization': 'false',
        'ui_telemetry_metadata': '{"openBuild": true}',
        'minuteman_forward_metrics': 'false',
        'minuteman_min_named_ip_erltuple': calculate_minuteman_min_named_ip_erltuple,
        'minuteman_max_named_ip_erltuple': calculate_minuteman_max_named_ip_erltuple,
        'mesos_isolation': calculate_mesos_isolation,
        'has_mesos_max_completed_tasks_per_framework': calculate_has_mesos_max_completed_tasks_per_framework,
        'config_yaml': calculate_config_yaml,
        'mesos_hooks': calculate_mesos_hooks,
        'use_mesos_hooks': calculate_use_mesos_hooks,
        'rexray_config_contents': calculate_rexray_config_contents,
        'no_proxy_final': calculate_no_proxy,
        'cluster_docker_credentials_path': calculate_cluster_docker_credentials_path,
        'cluster_docker_registry_enabled': calculate_cluster_docker_registry_enabled,
        'has_master_external_loadbalancer':
            lambda master_external_loadbalancer: calculate_set(master_external_loadbalancer),
        'cosmos_staged_package_storage_uri_flag':
            calculate_cosmos_staged_package_storage_uri_flag,
        'cosmos_package_storage_uri_flag':
            calculate_cosmos_package_storage_uri_flag,
        'profile_symlink_source': '/opt/mesosphere/bin/add_dcos_path.sh',
        'profile_symlink_target': '/etc/profile.d/dcos.sh',
        'profile_symlink_target_dir': calculate_profile_symlink_target_dir,
        'fair_sharing_excluded_resource_names': calculate_fair_sharing_excluded_resource_names,
        'check_config_contents': calculate_check_config_contents,
        'check_search_path': '/opt/mesosphere/bin:/usr/bin:/bin:/sbin',
        'check_ld_library_path': '/opt/mesosphere/lib'
    },
    'conditional': {
        'master_discovery': {
            'master_http_loadbalancer': {},
            'static': {
                'must': {'num_masters': calc_num_masters}
            }
        },
        'rexray_config_preset': {
            '': {},
            'aws': {
                'must': {
                    'rexray_config': json.dumps({
                        # Use IAM Instance Profile for auth.
                        'rexray': {
                            'loglevel': 'info',
                            'service': 'ebs'
                        },
                        'libstorage': {
                            'server': {
                                'tasks': {
                                    'logTimeout': '5m'
                                }
                            },
                            'integration': {
                                'volume': {
                                    'operations': {
                                        'unmount': {
                                            'ignoreusedcount': True
                                        }
                                    }
                                }
                            }
                        }
                    })
                }
            }
        }
    }
}
