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
import re
import socket
import string
from math import floor
from subprocess import check_output

import schema
import yaml

import gen.internals


DCOS_VERSION = '1.13.11-dev'

CHECK_SEARCH_PATH = '/opt/mesosphere/bin:/usr/bin:/bin:/sbin'


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
        assert low <= int_value, 'Must be above or equal to {}'.format(low)
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


def validate_absolute_path(path):
    if not path.startswith('/'):
        raise AssertionError('Must be an absolute filesystem path starting with /')


def valid_ipv6_address(ip6):
    try:
        socket.inet_pton(socket.AF_INET6, ip6)
        return True
    except OSError:
        return False
    except TypeError:
        return False


def validate_ipv6_addresses(ip6s: list):
    invalid_ip6s = []
    for ip6 in ip6s:
        if not valid_ipv6_address(ip6):
            invalid_ip6s.append(ip6)
    assert not invalid_ip6s, 'Invalid IPv6 addresses in list: {}'.format(', '.join(invalid_ip6s))


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
    assert mesos_container_log_sink in [
        'fluentbit',
        'journald',
        'logrotate',
        'fluentbit+logrotate',
        'journald+logrotate',
    ], "Container logs must go to 'fluentbit', 'journald', 'logrotate', 'fluentbit+logrotate', or 'journald+logrotate'."


def validate_metronome_gpu_scheduling_behavior(metronome_gpu_scheduling_behavior):
    assert metronome_gpu_scheduling_behavior in ['restricted', 'unrestricted', ''], \
        "metronome_gpu_scheduling_behavior must be 'restricted', 'unrestricted', 'undefined' or ''"


def validate_marathon_gpu_scheduling_behavior(marathon_gpu_scheduling_behavior):
    assert marathon_gpu_scheduling_behavior in ['restricted', 'unrestricted', ''], \
        "marathon_gpu_scheduling_behavior must be 'restricted', 'unrestricted', 'undefined' or ''"


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


def calculate_ip6_detect_contents(ip6_detect_filename):
    if ip6_detect_filename != '':
        return yaml.dump(open(ip6_detect_filename, encoding='utf-8').read())
    return yaml.dump("")


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


def validate_network_default_name(overlay_network_default_name, dcos_overlay_network):
    try:
        overlay_network = json.loads(dcos_overlay_network)
    except ValueError as ex:
        raise AssertionError("Provided input was not valid JSON: {}".format(dcos_overlay_network)) from ex

    overlay_names = map(lambda overlay: overlay['name'], overlay_network['overlays'])

    assert overlay_network_default_name in overlay_names, (
        "Default overlay network name does not reference a defined overlay network: {}".format(
            overlay_network_default_name))


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

    assert 'overlays' in overlay_network, (
        'Missing "overlays" in overlay configuration {}'.format(overlay_network))

    assert len(overlay_network['overlays']) > 0, (
        '"Overlays" network configuration is empty: {}'.format(overlay_network))

    for overlay in overlay_network['overlays']:
        assert 'name' in overlay, (
            'Missing "name" in overlay configuration: {}'.format(overlay))

        assert (len(overlay['name']) <= 13), (
            "Overlay name cannot exceed 13 characters:{}".format(overlay['name']))

        assert ('subnet' in overlay or 'subnet6' in overlay), (
            'Missing "subnet" or "subnet6" in overlay configuration:{}'.format(overlay))

        assert 'vtep_mac_oui' in overlay_network.keys(), (
            'Missing "vtep_mac_oui" in overlay configuration {}'.format(overlay_network))

        vtep_mtu = overlay_network.get('vtep_mtu', 1500)
        validate_int_in_range(vtep_mtu, 552, None)

        if 'subnet' in overlay:
            # Check the VTEP IP is present in the overlay configuration
            assert 'vtep_subnet' in overlay_network, (
                'Missing "vtep_subnet" in overlay configuration {}'.format(overlay_network))

            try:
                ipaddress.ip_network(overlay_network['vtep_subnet'])
            except ValueError as ex:
                raise AssertionError(
                    "Incorrect value for vtep_subnet: {}."
                    " Only IPv4 values are allowed".format(overlay_network['vtep_subnet'])) from ex
            try:
                ipaddress.ip_network(overlay['subnet'])
            except ValueError as ex:
                raise AssertionError(
                    "Incorrect value for overlay subnet {}."
                    " Only IPv4 values are allowed".format(overlay['subnet'])) from ex

        if 'subnet6' in overlay:
            # Check the VTEP IP6 is present in the overlay configuration
            assert 'vtep_subnet6' in overlay_network, (
                'Missing "vtep_subnet6" in overlay configuration {}'.format(overlay_network))

            try:
                ipaddress.ip_network(overlay_network['vtep_subnet6'])
            except ValueError as ex:
                raise AssertionError(
                    "Incorrect value for vtep_subnet6: {}."
                    " Only IPv6 values are allowed".format(overlay_network['vtep_subnet6'])) from ex
            try:
                ipaddress.ip_network(overlay['subnet6'])
            except ValueError as ex:
                raise AssertionError(
                    "Incorrect value for overlay subnet6 {}."
                    " Only IPv6 values are allowed".format(overlay_network['subnet6'])) from ex

        if 'enabled' in overlay:
            gen.internals.validate_one_of(overlay['enabled'], [True, False])


def calculate_dcos_overlay_network_json(dcos_overlay_network, enable_ipv6):
    overlay_network = json.loads(dcos_overlay_network)
    overlays = []
    for overlay in overlay_network['overlays']:
        if enable_ipv6 == 'false' and 'subnet' not in overlay:
            overlay['enabled'] = False
        overlays.append(overlay)
    overlay_network['overlays'] = overlays
    return json.dumps(overlay_network)


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


def calculate_mesos_isolation(enable_gpu_isolation, mesos_seccomp_enabled):
    isolators = ('cgroups/all,disk/du,network/cni,filesystem/linux,docker/runtime,docker/volume,'
                 'volume/sandbox_path,volume/secret,posix/rlimits,namespaces/pid,linux/capabilities,'
                 'com_mesosphere_dcos_MetricsIsolatorModule')
    if enable_gpu_isolation == 'true':
        isolators += ',gpu/nvidia'
    if mesos_seccomp_enabled == 'true':
        isolators += ',linux/seccomp'
    return isolators


def validate_os_type(os_type):
    gen.internals.validate_one_of(os_type, ['coreos', 'el7'])


def validate_bootstrap_tmp_dir(bootstrap_tmp_dir):
    # Must be non_empty
    assert bootstrap_tmp_dir, "Must not be empty"

    # Should not start or end with `/`
    assert bootstrap_tmp_dir[0] != '/' and bootstrap_tmp_dir[-1] != 0, \
        "Must be an absolute path to a directory, although leave off the `/` at the beginning and end."


def calculate_dcos_l4lb_min_named_ip_erltuple(dcos_l4lb_min_named_ip):
    return ip_to_erltuple(dcos_l4lb_min_named_ip)


def calculate_dcos_l4lb_max_named_ip_erltuple(dcos_l4lb_max_named_ip):
    return ip_to_erltuple(dcos_l4lb_max_named_ip)


def ip_to_erltuple(ip):
    return '{' + ip.replace('.', ',') + '}'


def validate_dcos_l4lb_min_named_ip(dcos_l4lb_min_named_ip):
    validate_ipv4_addresses([dcos_l4lb_min_named_ip])


def validate_dcos_l4lb_max_named_ip(dcos_l4lb_max_named_ip):
    validate_ipv4_addresses([dcos_l4lb_max_named_ip])


def calculate_dcos_l4lb_min_named_ip6_erltuple(dcos_l4lb_min_named_ip6):
    return ip6_to_erltuple(dcos_l4lb_min_named_ip6)


def calculate_dcos_l4lb_max_named_ip6_erltuple(dcos_l4lb_max_named_ip6):
    return ip6_to_erltuple(dcos_l4lb_max_named_ip6)


def ip6_to_erltuple(ip6):
    expanded_ip6 = ipaddress.ip_address(ip6).exploded.replace('000', '')
    return '{16#' + expanded_ip6.replace(':', ',16#') + '}'


def validate_dcos_l4lb_min_named_ip6(dcos_l4lb_min_named_ip6):
    validate_ipv6_addresses([dcos_l4lb_min_named_ip6])


def validate_dcos_l4lb_max_named_ip6(dcos_l4lb_max_named_ip6):
    validate_ipv6_addresses([dcos_l4lb_max_named_ip6])


def validate_dcos_l4lb_enable_ipv6(dcos_l4lb_enable_ipv6, enable_ipv6):
    validate_true_false(dcos_l4lb_enable_ipv6)
    if enable_ipv6 == 'false':
        assert dcos_l4lb_enable_ipv6 == 'false', "When enable_ipv6 is false, " \
            "dcos_l4lb_enable_ipv6 must be false as well"


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


def calculate_adminrouter_tls_version_override(
        adminrouter_tls_1_0_enabled,
        adminrouter_tls_1_1_enabled,
        adminrouter_tls_1_2_enabled):
    tls_versions = list()
    if adminrouter_tls_1_0_enabled == 'true':
        tls_versions.append('TLSv1')

    if adminrouter_tls_1_1_enabled == 'true':
        tls_versions.append('TLSv1.1')

    if adminrouter_tls_1_2_enabled == 'true':
        tls_versions.append('TLSv1.2')

    tls_version_string = " ".join(tls_versions)
    return tls_version_string


def calculate_adminrouter_tls_cipher_override(adminrouter_tls_cipher_suite):
    if adminrouter_tls_cipher_suite != '':
        return 'true'
    else:
        return 'false'


def validate_adminrouter_tls_version_present(
        adminrouter_tls_1_0_enabled,
        adminrouter_tls_1_1_enabled,
        adminrouter_tls_1_2_enabled):

    tls_version_flags = [
        adminrouter_tls_1_0_enabled,
        adminrouter_tls_1_1_enabled,
        adminrouter_tls_1_2_enabled,
    ]

    enabled_tls_flags_count = len(
        [flag for flag in tls_version_flags if flag == 'true'])

    msg = (
        'At least one of adminrouter_tls_1_0_enabled, '
        'adminrouter_tls_1_1_enabled and adminrouter_tls_1_2_enabled must be '
        "set to 'true'."
    )
    assert enabled_tls_flags_count > 0, msg


def validate_adminrouter_x_frame_options(adminrouter_x_frame_options):
    """
    Provide a basic validation that checks that provided value starts with
    one of the supported options: DENY, SAMEORIGIN, ALLOW-FROM
    See: https://tools.ietf.org/html/rfc7034#section-2.1
    """
    msg = 'X-Frame-Options must be set to one of DENY, SAMEORIGIN, ALLOW-FROM'
    regex = r"^(DENY|SAMEORIGIN|ALLOW-FROM[ \t].+)$"
    match = re.match(regex, adminrouter_x_frame_options, re.IGNORECASE)
    assert match is not None, msg


def validate_s3_prefix(s3_prefix):
    # See DCOS_OSS-1353
    assert not s3_prefix.endswith('/'), "Must be a file path and cannot end in a /"


def validate_dns_bind_ip_blacklist(dns_bind_ip_blacklist):
    return validate_ip_list(dns_bind_ip_blacklist)


def calculate_dns_bind_ip_blacklist_json(dns_bind_ip_blacklist, dns_bind_ip_reserved):
    ips = validate_json_list(dns_bind_ip_blacklist)
    reserved_ips = validate_json_list(dns_bind_ip_reserved)
    return json.dumps(reserved_ips + ips)


def validate_dns_forward_zones(dns_forward_zones):
    """
     "forward_zones": {"a.contoso.com": ["1.1.1.1:53", "2.2.2.2"],
                       "b.contoso.com": ["3.3.3.3:53", "4.4.4.4"]}
    """

    def fz_err(msg, *argv):
        msg = msg.format(*argv)
        return 'Invalid "dns_forward_zones": {}'.format(msg)

    zone_defs = None
    try:
        zone_defs = json.loads(dns_forward_zones)
    except ValueError as ex:
        error = fz_err("{} is not valid JSON: {}", dns_forward_zones, ex)
        raise AssertionError(error) from ex

    assert isinstance(zone_defs, dict), fz_err("{} is not a a dict", zone_defs)

    for k, upstreams in zone_defs.items():
        assert isinstance(upstreams, list), fz_err("{} is not a list", upstreams)
        for upstr in upstreams:
            assert isinstance(upstr, str), fz_err("{} is not a string", upstr)
            ip, sep, port = upstr.rpartition(':')
            if sep:
                validate_int_in_range(port, 1, 65535)
            else:
                ip = upstr
            assert valid_ipv4_address(ip), fz_err("{} not a valid IP address", ip)


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


def validate_mesos_recovery_timeout(mesos_recovery_timeout):
    units = ['ns', 'us', 'ms', 'secs', 'mins', 'hrs', 'days', 'weeks']

    match = re.match("([\d\.]+)(\w+)", mesos_recovery_timeout)
    assert match is not None, "Error parsing 'mesos_recovery_timeout' value: {}.".format(mesos_recovery_timeout)

    value = match.group(1)
    unit = match.group(2)

    assert value.count('.') <= 1, "Invalid decimal format."
    assert float(value) <= 2**64, "Value {} not in supported range.".format(value)
    assert unit in units, "Unit '{}' not in {}.".format(unit, units)


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


def validate_superuser_credentials_not_partially_given(
        superuser_service_account_uid, superuser_service_account_public_key):
    pair = (superuser_service_account_uid, superuser_service_account_public_key)

    if any(pair) and not all(pair):
        raise AssertionError(
            "'superuser_service_account_uid' and "
            "'superuser_service_account_public_key' "
            "must both be empty or both be non-empty"
        )


def calculate__superuser_service_account_public_key_json(
        superuser_service_account_public_key):
    """
    This function expects PEM text as input, parses and validates it, and emits
    JSON-encoded PEM text as output. That includes wrapping the text in double
    quotes, and escaping newline characters.
    """
    import cryptography.hazmat.backends
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    assert isinstance(superuser_service_account_public_key, str)

    def validate_rsa_pubkey(key_pem):
        """
        Check if `key_pem` is a string containing an RSA public key encoded
        using the X.509 SubjectPublicKeyInfo/OpenSSL PEM public key format.
        Refs:
            - https://tools.ietf.org/html/rfc5280.html
            - http://stackoverflow.com/a/29707204/145400

        Args:
            key_pem (str): serialized public key
        """
        # This will raise `ValueError` for invalid input or
        # `UnsupportedAlgorithm` for exotic unsupported key types.
        try:
            key = serialization.load_pem_public_key(
                data=key_pem.encode('ascii'),
                backend=cryptography.hazmat.backends.default_backend()
            )
        except ValueError as exc:
            raise AssertionError(
                'superuser_service_account_public_key has an invalid value. It '
                'must hold an RSA public key encoded in the OpenSSL PEM '
                'format. Error: %s' % (exc, )
            )

        assert isinstance(key, rsa.RSAPublicKey), \
            'superuser_service_account_public_key must be of type RSA'

    if superuser_service_account_public_key:
        validate_rsa_pubkey(superuser_service_account_public_key)

    # Escape special characters like newlines, and add quotes (for the common
    # case of `superuser_service_account_public_key` being empty this returns
    # '""'.)
    return json.dumps(superuser_service_account_public_key)


def calculate_check_config(check_time):
    # We consider only two timeouts:
    # * 1s for immediate checks (such as checking for the presence of CLI utilities).
    # * 30s for any check which is expected to take more than 5s.
    #
    # The 30s value was chosen arbitrarily. It may be increased in the future as required.
    # We chose not to use a value greater than 1min, as the checks are automatically executed
    # in parallel every minute.
    instant_check_timeout = "5s"
    normal_check_timeout = "30s"
    check_config = {
        'node_checks': {
            'checks': {
                'components_master': {
                    'description': 'All DC/OS components are healthy.',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', '--role', 'master', 'components',
                            '--exclude=dcos-checks-poststart.timer,dcos-checks-poststart.service'],
                    'timeout': normal_check_timeout,
                    'roles': ['master']
                },
                'components_agent': {
                    'description': 'All DC/OS components are healthy',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', '--role', 'agent', 'components', '--port', '61001',
                            '--exclude=dcos-checks-poststart.service,dcos-checks-poststart.timer'],
                    'timeout': normal_check_timeout,
                    'roles': ['agent']
                },
                'xz': {
                    'description': 'The xz utility is available',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', 'executable', 'xz'],
                    'timeout': instant_check_timeout
                },
                'tar': {
                    'description': 'The tar utility is available',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', 'executable', 'tar'],
                    'timeout': instant_check_timeout
                },
                'curl': {
                    'description': 'The curl utility is available',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', 'executable', 'curl'],
                    'timeout': instant_check_timeout
                },
                'unzip': {
                    'description': 'The unzip utility is available',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', 'executable', 'unzip'],
                    'timeout': instant_check_timeout
                },
                'ip_detect_script': {
                    'description': 'The IP detect script produces valid output',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', 'ip'],
                    'timeout': normal_check_timeout
                },
                'docker': {
                    'description': 'Docker is installed',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', 'executable', 'docker'],
                    'timeout': normal_check_timeout
                },
                'mesos_master_replog_synchronized': {
                    'description': 'The Mesos master has synchronized its replicated log',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', '--role', 'master', 'mesos-metrics'],
                    'timeout': normal_check_timeout,
                    'roles': ['master']
                },
                'mesos_agent_registered_with_masters': {
                    'description': 'The Mesos agent has registered with the masters',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', '--role', 'agent', 'mesos-metrics'],
                    'timeout': normal_check_timeout,
                    'roles': ['agent']
                },
                'journald_dir_permissions': {
                    'description': 'Journald directory has the right owners and permissions',
                    'cmd': ['/opt/mesosphere/bin/dcos-checks', 'journald'],
                    'timeout': instant_check_timeout,
                },
                'cockroachdb_replication': {
                    'description': 'CockroachDB is fully replicated',
                    'cmd': [
                        '/opt/mesosphere/bin/dcos-checks',
                        'cockroachdb',
                        'ranges',
                    ],
                    'timeout': normal_check_timeout,
                    'roles': ['master']
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
                'docker',
                'ip_detect_script',
                'mesos_master_replog_synchronized',
                'mesos_agent_registered_with_masters',
                'journald_dir_permissions',
                'cockroachdb_replication',
            ],
        },
    }

    if check_time == 'true':
        # Add the clock sync check.
        clock_sync_check_name = 'clock_sync'
        check_config['node_checks']['checks'][clock_sync_check_name] = {
            'description': 'System clock is in sync.',
            'cmd': ['/opt/mesosphere/bin/dcos-checks', 'time'],
            'timeout': instant_check_timeout
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


def calculate_fault_domain_detect_contents(fault_domain_detect_filename):
    if os.path.exists(fault_domain_detect_filename):
        return yaml.dump(open(fault_domain_detect_filename, encoding='utf-8').read())
    return ''


__dcos_overlay_network_default_name = 'dcos'
__dcos_overlay_network6_default_name = 'dcos6'


# Note(JP): let us try to distinguish private from public configuration
# parameters by adding an underscore prefix to private ones. Private
# configuration parameters are not meant to be set in the DC/OS config yaml
# document. Only public ones are meant to be set there. Only public
# configuration parameters are meant to be publicly documented.


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
        validate_superuser_credentials_not_partially_given,
        lambda auth_cookie_secure_flag: validate_true_false(auth_cookie_secure_flag),
        lambda oauth_enabled: validate_true_false(oauth_enabled),
        lambda oauth_available: validate_true_false(oauth_available),
        validate_mesos_dns_ip_sources,
        lambda mesos_dns_set_truncate_bit: validate_true_false(mesos_dns_set_truncate_bit),
        validate_mesos_log_retention_mb,
        lambda telemetry_enabled: validate_true_false(telemetry_enabled),
        lambda master_dns_bindall: validate_true_false(master_dns_bindall),
        validate_os_type,
        validate_dcos_overlay_network,
        lambda dcos_overlay_network_json: validate_dcos_overlay_network(dcos_overlay_network_json),
        validate_dcos_ucr_default_bridge_subnet,
        lambda dcos_net_cluster_identity: validate_true_false(dcos_net_cluster_identity),
        lambda dcos_net_rest_enable: validate_true_false(dcos_net_rest_enable),
        lambda dcos_net_watchdog: validate_true_false(dcos_net_watchdog),
        lambda dcos_overlay_network_default_name, dcos_overlay_network:
            validate_network_default_name(dcos_overlay_network_default_name, dcos_overlay_network),
        lambda dcos_overlay_enable: validate_true_false(dcos_overlay_enable),
        lambda dcos_overlay_mtu: validate_int_in_range(dcos_overlay_mtu, 552, None),
        lambda dcos_overlay_config_attempts: validate_int_in_range(dcos_overlay_config_attempts, 0, 10),
        lambda dcos_remove_dockercfg_enable: validate_true_false(dcos_remove_dockercfg_enable),
        lambda rexray_config: validate_json_dictionary(rexray_config),
        lambda check_time: validate_true_false(check_time),
        lambda enable_gpu_isolation: validate_true_false(enable_gpu_isolation),
        validate_dcos_l4lb_min_named_ip,
        validate_dcos_l4lb_max_named_ip,
        validate_dcos_l4lb_min_named_ip6,
        validate_dcos_l4lb_max_named_ip6,
        validate_dcos_l4lb_enable_ipv6,
        lambda dcos_l4lb_enable_ipset: validate_true_false(dcos_l4lb_enable_ipset),
        lambda dcos_dns_push_ops_timeout: validate_int_in_range(dcos_dns_push_ops_timeout, 50, 120000),
        lambda cluster_docker_credentials_dcos_owned: validate_true_false(cluster_docker_credentials_dcos_owned),
        lambda cluster_docker_credentials_enabled: validate_true_false(cluster_docker_credentials_enabled),
        lambda cluster_docker_credentials_write_to_etc: validate_true_false(cluster_docker_credentials_write_to_etc),
        lambda cluster_docker_credentials: validate_json_dictionary(cluster_docker_credentials),
        lambda aws_masters_have_public_ip: validate_true_false(aws_masters_have_public_ip),
        validate_exhibitor_storage_master_discovery,
        lambda exhibitor_admin_password_enabled: validate_true_false(exhibitor_admin_password_enabled),
        lambda enable_lb: validate_true_false(enable_lb),
        lambda enable_ipv6: validate_true_false(enable_ipv6),
        lambda adminrouter_tls_1_0_enabled: validate_true_false(adminrouter_tls_1_0_enabled),
        lambda adminrouter_tls_1_1_enabled: validate_true_false(adminrouter_tls_1_1_enabled),
        lambda adminrouter_tls_1_2_enabled: validate_true_false(adminrouter_tls_1_2_enabled),
        validate_adminrouter_tls_version_present,
        validate_adminrouter_x_frame_options,
        lambda gpus_are_scarce: validate_true_false(gpus_are_scarce),
        validate_mesos_max_completed_tasks_per_framework,
        validate_mesos_recovery_timeout,
        validate_metronome_gpu_scheduling_behavior,
        lambda mesos_seccomp_enabled: validate_true_false(mesos_seccomp_enabled),
        lambda check_config: validate_check_config(check_config),
        lambda custom_checks: validate_check_config(custom_checks),
        lambda custom_checks, check_config: validate_custom_checks(custom_checks, check_config),
        lambda fault_domain_enabled: validate_true_false(fault_domain_enabled),
        lambda mesos_master_work_dir: validate_absolute_path(mesos_master_work_dir),
        lambda mesos_agent_work_dir: validate_absolute_path(mesos_agent_work_dir),
        lambda mesos_agent_log_file: validate_absolute_path(mesos_agent_log_file),
        lambda mesos_master_log_file: validate_absolute_path(mesos_master_log_file),
        lambda diagnostics_bundles_dir: validate_absolute_path(diagnostics_bundles_dir),
        lambda licensing_enabled: validate_true_false(licensing_enabled),
        lambda enable_mesos_ipv6_discovery: validate_true_false(enable_mesos_ipv6_discovery),
        lambda log_offers: validate_true_false(log_offers),
        lambda mesos_cni_root_dir_persist: validate_true_false(mesos_cni_root_dir_persist),
        lambda enable_mesos_input_plugin: validate_true_false(enable_mesos_input_plugin),
    ],
    'default': {
        'exhibitor_azure_account_key': '',
        'aws_secret_access_key': '',
        'bootstrap_tmp_dir': 'tmp',
        'bootstrap_variant': lambda: calculate_environment_variable('BOOTSTRAP_VARIANT'),
        'dns_bind_ip_reserved': '["198.51.100.4"]',
        'dns_bind_ip_blacklist': '[]',
        'dns_forward_zones': '{}',
        'use_proxy': 'false',
        'weights': '',
        'adminrouter_auth_enabled': calculate_adminrouter_auth_enabled,
        'adminrouter_tls_1_0_enabled': 'false',
        'adminrouter_tls_1_1_enabled': 'false',
        'adminrouter_tls_1_2_enabled': 'true',
        'adminrouter_tls_cipher_suite': '',
        'adminrouter_x_frame_options': 'DENY',
        'intercom_enabled': 'true',
        'oauth_enabled': 'true',
        'oauth_available': 'true',
        'telemetry_enabled': 'true',
        'check_time': 'true',
        'enable_lb': 'true',
        'enable_ipv6': 'true',
        'docker_remove_delay': '1hrs',
        'docker_stop_timeout': '20secs',
        'gc_delay': '2days',
        'ip_detect_contents': calculate_ip_detect_contents,
        'ip_detect_public_filename': '',
        'ip_detect_public_contents': calculate_ip_detect_public_contents,
        'ip6_detect_contents': calculate_ip6_detect_contents,
        'dns_search': '',
        'auth_cookie_secure_flag': 'false',
        'marathon_java_args': '',
        'master_dns_bindall': 'true',
        'mesos_dns_ip_sources': '["host", "netinfo"]',
        'mesos_dns_set_truncate_bit': 'true',
        'master_external_loadbalancer': '',
        'mesos_log_retention_mb': '4000',
        'mesos_container_log_sink': 'fluentbit+logrotate',
        'mesos_max_completed_tasks_per_framework': '',
        'mesos_recovery_timeout': '24hrs',
        'mesos_seccomp_enabled': 'false',
        'mesos_seccomp_profile_name': '',
        'metronome_gpu_scheduling_behavior': 'restricted',
        'marathon_gpu_scheduling_behavior': 'restricted',
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
        'ui_update_enabled': 'true',
        'dcos_net_cluster_identity': 'false',
        'dcos_net_rest_enable': "true",
        'dcos_net_watchdog': "true",
        'dcos_cni_data_dir': '/var/run/dcos/cni/networks',
        'dcos_overlay_config_attempts': '4',
        'dcos_overlay_mtu': '1420',
        'dcos_overlay_enable': "true",
        'dcos_overlay_network_json': calculate_dcos_overlay_network_json,
        'dcos_overlay_network': json.dumps({
            'vtep_subnet': '44.128.0.0/20',
            'vtep_subnet6': 'fd01:a::/64',
            'vtep_mac_oui': '70:B3:D5:00:00:00',
            'overlays': [{
                'name': __dcos_overlay_network_default_name,
                'subnet': '9.0.0.0/8',
                'prefix': 24
            }, {
                'name': __dcos_overlay_network6_default_name,
                'subnet6': 'fd01:b::/64',
                'prefix6': 80
            }]
        }),
        'dcos_overlay_network_default_name': __dcos_overlay_network_default_name,
        'dcos_overlay_network6_default_name': __dcos_overlay_network6_default_name,
        'dcos_ucr_default_bridge_network_name': 'mesos-bridge',
        'dcos_ucr_default_bridge_subnet': '172.31.254.0/24',
        'dcos_remove_dockercfg_enable': "false",
        'dcos_l4lb_min_named_ip': '11.0.0.0',
        'dcos_l4lb_max_named_ip': '11.255.255.255',
        'dcos_l4lb_min_named_ip6': 'fd01:c::',
        'dcos_l4lb_max_named_ip6': 'fd01:c::ffff:ffff:ffff:ffff',
        'dcos_l4lb_enable_ipv6': 'true',
        'dcos_l4lb_enable_ipset': 'true',
        'dcos_dns_push_ops_timeout': '1000',
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
        'superuser_service_account_uid': '',
        'superuser_service_account_public_key': '',
        '_superuser_service_account_public_key_json': calculate__superuser_service_account_public_key_json,
        'enable_gpu_isolation': 'true',
        'cluster_docker_registry_url': '',
        'cluster_docker_credentials_dcos_owned': calculate_docker_credentials_dcos_owned,
        'cluster_docker_credentials_write_to_etc': 'false',
        'cluster_docker_credentials_enabled': 'false',
        'cluster_docker_credentials': "{}",
        'gpus_are_scarce': 'true',
        'check_config': calculate_check_config,
        'custom_checks': '{}',
        'check_search_path': CHECK_SEARCH_PATH,
        'mesos_master_work_dir': '/var/lib/dcos/mesos/master',
        'mesos_agent_work_dir': '/var/lib/mesos/slave',
        'diagnostics_bundles_dir': '/var/lib/dcos/dcos-diagnostics/diag-bundles',
        'fault_domain_detect_filename': 'genconf/fault-domain-detect',
        'fault_domain_detect_contents': calculate_fault_domain_detect_contents,
        'license_key_contents': '',
        'enable_mesos_ipv6_discovery': 'false',
        'log_offers': 'true',
        'mesos_cni_root_dir_persist': 'false',
        'enable_mesos_input_plugin': 'true'
    },
    'must': {
        'fault_domain_enabled': 'false',
        'custom_auth': 'false',
        'master_quorum': lambda num_masters: str(floor(int(num_masters) / 2) + 1),
        'dns_bind_ip_blacklist_json': calculate_dns_bind_ip_blacklist_json,
        'resolvers_str': calculate_resolvers_str,
        'dcos_image_commit': calulate_dcos_image_commit,
        'mesos_dns_resolvers_str': calculate_mesos_dns_resolvers_str,
        'mesos_log_retention_count': calculate_mesos_log_retention_count,
        'mesos_log_directory_max_files': calculate_mesos_log_directory_max_files,
        'mesos_agent_log_file': '/var/log/mesos/mesos-agent.log',
        'mesos_master_log_file': '/var/lib/dcos/mesos/log/mesos-master.log',
        'marathon_port': '8080',
        'dcos_version': DCOS_VERSION,
        'dcos_variant': 'open',
        'dcos_gen_resolvconf_search_str': calculate_gen_resolvconf_search,
        'curly_pound': '{#',
        'exhibitor_static_ensemble': calculate_exhibitor_static_ensemble,
        'exhibitor_admin_password_enabled': calculate_exhibitor_admin_password_enabled,
        'ui_branding': 'false',
        'ui_external_links': 'false',
        'ui_networking': 'false',
        'ui_organization': 'false',
        'ui_telemetry_metadata': '{"openBuild": true}',
        'dcos_l4lb_forward_metrics': 'false',
        'dcos_l4lb_min_named_ip_erltuple': calculate_dcos_l4lb_min_named_ip_erltuple,
        'dcos_l4lb_max_named_ip_erltuple': calculate_dcos_l4lb_max_named_ip_erltuple,
        'dcos_l4lb_min_named_ip6_erltuple': calculate_dcos_l4lb_min_named_ip6_erltuple,
        'dcos_l4lb_max_named_ip6_erltuple': calculate_dcos_l4lb_max_named_ip6_erltuple,
        'mesos_isolation': calculate_mesos_isolation,
        'has_mesos_max_completed_tasks_per_framework': calculate_has_mesos_max_completed_tasks_per_framework,
        'has_mesos_seccomp_profile_name':
            lambda mesos_seccomp_profile_name: calculate_set(mesos_seccomp_profile_name),
        'mesos_hooks': calculate_mesos_hooks,
        'use_mesos_hooks': calculate_use_mesos_hooks,
        'rexray_config_contents': calculate_rexray_config_contents,
        'no_proxy_final': calculate_no_proxy,
        'cluster_docker_credentials_path': calculate_cluster_docker_credentials_path,
        'cluster_docker_registry_enabled': calculate_cluster_docker_registry_enabled,
        'has_master_external_loadbalancer':
            lambda master_external_loadbalancer: calculate_set(master_external_loadbalancer),
        'profile_symlink_source': '/opt/mesosphere/bin/add_dcos_path.sh',
        'profile_symlink_target': '/etc/profile.d/dcos.sh',
        'profile_symlink_target_dir': calculate_profile_symlink_target_dir,
        'fair_sharing_excluded_resource_names': calculate_fair_sharing_excluded_resource_names,
        'check_config_contents': calculate_check_config_contents,
        'check_ld_library_path': '/opt/mesosphere/lib',
        'adminrouter_tls_version_override': calculate_adminrouter_tls_version_override,
        'adminrouter_tls_cipher_override': calculate_adminrouter_tls_cipher_override,
        'licensing_enabled': 'false',
        'has_metronome_gpu_scheduling_behavior':
            lambda metronome_gpu_scheduling_behavior: calculate_set(metronome_gpu_scheduling_behavior),
        'has_marathon_gpu_scheduling_behavior':
            lambda marathon_gpu_scheduling_behavior: calculate_set(marathon_gpu_scheduling_behavior),

    },
    'secret': [
        'cluster_docker_credentials',
        'exhibitor_admin_password',
        'exhibitor_azure_account_key',
        'aws_secret_access_key'
    ],
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
