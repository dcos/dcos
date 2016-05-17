import json
import os
import socket
from math import floor
from subprocess import check_output

import yaml

import gen.aws.calc
import gen.azure.calc
import pkgpanda.exceptions
from pkgpanda import PackageId
from pkgpanda.build import hash_checkout


def calculate_bootstrap_variant():
    variant = os.getenv('BOOTSTRAP_VARIANT')
    assert variant is not None, "BOOTSTRAP_VARIANT must be set"
    return variant


def calulate_dcos_image_commit():
    dcos_image_commit = os.getenv('DCOS_IMAGE_COMMIT', None)

    if dcos_image_commit is None:
        dcos_image_commit = check_output(['git', 'rev-parse', 'HEAD']).decode('utf-8').strip()

    if dcos_image_commit is None:
        raise "Unable to set dcos_image_commit from teamcity or git."

    return dcos_image_commit


def calculate_resolvers_str(resolvers):
    # Validation because accidentally slicing a string instead of indexing a
    # list of resolvers then finding out at cluster launch is painful.
    assert isinstance(resolvers, str)
    resolvers = json.loads(resolvers)
    assert isinstance(resolvers, list)
    return ",".join(resolvers)


def calculate_mesos_dns_resolvers_str(resolvers):
    assert isinstance(resolvers, str)
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


def calculate_ip_detect_contents(ip_detect_filename):
    assert os.path.exists(ip_detect_filename), "ip-detect script: {} must exist".format(ip_detect_filename)
    return yaml.dump(open(ip_detect_filename, encoding='utf-8').read())


def calculate_gen_resolvconf_search(dns_search):
    if len(dns_search) > 0:
        return "SEARCH=" + dns_search
    else:
        return ""


def calculate_mesos_hooks_env_var(mesos_hooks):
    if mesos_hooks == '':
        return ''
    return 'MESOS_HOOKS=' + mesos_hooks


def calculate_mesos_slave_modules_json(mesos_slave_modules):
    # Ensure that this file is readable by humans by including newlines in the output.
    json_multiline = json.dumps({"libraries": mesos_slave_modules}, indent=2)
    # Preserve indentation in dcos-config.yaml's template by adding indentation to this content
    injected_indent = 6 * ' '
    return json_multiline.replace('\n', '\n' + injected_indent)


def validate_telemetry_enabled(telemetry_enabled):
    can_be = ['true', 'false']
    assert telemetry_enabled in can_be, 'Must be one of {}. Got {}.'.format(can_be, telemetry_enabled)


def validate_oauth_enabled(oauth_enabled):
    # Should correspond with oauth_enabled in gen/azure/calc.py
    if oauth_enabled in ["[[[variables('oauthEnabled')]]]", '{ "Ref" : "OAuthEnabled" }']:
        return
    can_be = ['true', 'false']
    assert oauth_enabled in can_be, 'Must be one of {}. Got {}'.format(can_be, oauth_enabled)


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


def validate_json_list(json_list):
    try:
        list_data = json.loads(json_list)

        assert type(list_data) is list, "Must be a JSON list. Got a {}".format(type(list_data))
    except json.JSONDecodeError as ex:
        assert False, "Must be a valid JSON list. Errors while parsing at position {}: {}".format(ex.pos, ex.msg)

    return list_data


def validate_host_list(host_list):
    host_list = validate_json_list(host_list)
    azure_format_check = []
    validate_duplicates(host_list)
    for host in host_list:
        assert isinstance(host, str), 'Host must be of type string, got {}'.format(type(host))
        if host.startswith('[[[reference(') and host.endswith(').ipConfigurations[0].properties.privateIPAddress]]]'):  # noqa
            azure_format_check.append(True)
        else:
            azure_format_check.append(False)
    if all(azure_format_check):
        return host_list
    assert not any(azure_format_check), "Azure static master list and IP based static master list cannot be mixed. Use "
    "either all Azure IP references or IPv4 addresses."
    return validate_ipv4_addrs(host_list)


def validate_ipv4_addrs(ips):
    assert isinstance(ips, list)
    invalid_ips = []
    for ip in ips:
        try:
            socket.inet_pton(socket.AF_INET, str(ip))
        except OSError:
            invalid_ips.append(ip)
    assert not len(invalid_ips), 'Only IPv4 values are allowed. The following are invalid IPv4 addresses: {}'.format(
                                 ', '.join(invalid_ips))
    return ips


def validate_duplicates(input_list):
    assert isinstance(input_list, list)
    dups = list(filter(lambda x: input_list.count(x) > 1, input_list))
    assert len(dups) == 0, "List cannot contain duplicates: {}".format(", ".join(dups))


def validate_master_list(master_list):
    return validate_host_list(master_list)


def validate_resolvers(resolvers):
    return validate_host_list(resolvers)


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


def validate_zk_hosts(exhibitor_zk_hosts):
    # TODO(malnick) Add validation of IPv4 address and port to this
    assert not exhibitor_zk_hosts.startswith('zk://'), "Must be of the form `host:port,host:port', not start with zk://"


def validate_zk_path(exhibitor_zk_path):
    assert exhibitor_zk_path.startswith('/'), "Must be of the form /path/to/znode"


def calculate_exhibitor_static_ensemble(master_list):
    masters = json.loads(master_list)
    masters.sort()
    return ','.join(['%d:%s' % (i+1, m) for i, m in enumerate(masters)])


__logrotate_slave_module_name = 'org_apache_mesos_LogrotateContainerLogger'
__logrotate_slave_module = {
    'file': '/opt/mesosphere/lib/liblogrotate_container_logger.so',
    'modules': [{
        'name': __logrotate_slave_module_name,
        'parameters': [
            {'key': 'launcher_dir', 'value': '/opt/mesosphere/active/mesos/libexec/mesos/'},
            {'key': 'max_stdout_size', 'value': '2MB'},
            {'key': 'logrotate_stdout_options', 'value': 'rotate 9'},
            {'key': 'max_stderr_size', 'value': '2MB'},
            {'key': 'logrotate_stderr_options', 'value': 'rotate 9'},
        ]
    }]
}

__stats_isolator_slave_module_name = 'com_mesosphere_StatsIsolatorModule'
__stats_hook_slave_module_name = 'com_mesosphere_StatsEnvHook'
__stats_slave_module = {
    'file': '/opt/mesosphere/lib/libstats-slave.so',
    'modules': [{
        'name': __stats_isolator_slave_module_name,
    }, {
        'name': __stats_hook_slave_module_name,
        'parameters': [
            {'key': 'dest_host', 'value': 'metrics.marathon.mesos'},
            {'key': 'dest_port', 'value': '8125'},
            {'key': 'dest_refresh_seconds', 'value': '60'},
            {'key': 'listen_host', 'value': '127.0.0.1'},
            {'key': 'listen_port_mode', 'value': 'ephemeral'},
            {'key': 'annotation_mode', 'value': 'key_prefix'},
            {'key': 'chunking', 'value': 'true'},
            {'key': 'chunk_size_bytes', 'value': '512'},
        ]
    }]
}

__default_mesos_slave_modules = [
    __logrotate_slave_module,
]

__default_isolation_modules = [
    'cgroups/cpu',
    'cgroups/mem',
    'posix/disk',
]


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
        validate_telemetry_enabled],
    'default': {
        'bootstrap_variant': calculate_bootstrap_variant,
        'weights': '',
        'oauth_enabled': 'true',
        'oauth_available': calculate_oauth_available,
        'telemetry_enabled': 'true',
        'docker_remove_delay': '1hrs',
        'gc_delay': '2days',
        'ip_detect_contents': calculate_ip_detect_contents,
        'dns_search': '',
        'auth_cookie_secure_flag': 'false',
        'mesos_dns_ip_sources': '["host", "netinfo"]',
        'mesos_container_logger': __logrotate_slave_module_name,
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
        'ui_banner_dismissible': 'null'
    },
    'must': {
        'master_quorum': lambda num_masters: str(floor(int(num_masters) / 2) + 1),
        'resolvers_str': calculate_resolvers_str,
        'dcos_image_commit': calulate_dcos_image_commit,
        'mesos_dns_resolvers_str': calculate_mesos_dns_resolvers_str,
        'dcos_version': '1.8-dev',
        'dcos_gen_resolvconf_search_str': calculate_gen_resolvconf_search,
        'curly_pound': '{#',
        'cluster_packages': calculate_cluster_packages,
        'config_id': calculate_config_id,
        'mesos_hooks_env_var': calculate_mesos_hooks_env_var,
        'exhibitor_static_ensemble': calculate_exhibitor_static_ensemble,
        'ui_branding': 'false',
        'ui_external_links': 'false',
        'ui_networking': 'false',
        'ui_organization': 'false',
        'mesos_isolation_modules': ','.join(__default_isolation_modules),
        'mesos_hooks': '',
        'mesos_slave_modules_json': calculate_mesos_slave_modules_json(
            __default_mesos_slave_modules),
        'minuteman_forward_metrics': 'false',
    },
    'conditional': {
        'master_discovery': {
            'master_http_loadbalancer': {},
            'vrrp': {},
            'static': {
                'must': {'num_masters': calc_num_masters}
            }
        },
        'provider': {
            'onprem': {
                'default': {
                    'resolvers': '["8.8.8.8", "8.8.4.4"]'
                },
            },
            'azure': gen.azure.calc.entry,
            'aws': gen.aws.calc.entry,
            'other': {}
        },
    }
}
