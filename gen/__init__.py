"""Helps build config packages for installer-specific templates.

Takes in a bunch of configuration files, as well as functions to calculate the values/strings which
need to be put into the configuration.

Operates strictly:
  - All paramaters are strings. All things calculated / derived are strings.
  - Every given parameter must map to some real config option.
  - Every config option must be given only once.
  - Defaults can be overridden. If no default is given, the parameter must be specified
  - empty string is not the same as "not specified"
"""

import importlib.machinery
import json
import logging as log
import os
import os.path
import pprint
import textwrap
from copy import copy, deepcopy
from typing import List

import yaml

import gen.calc
import gen.internals
import gen.template
import gen.util
from gen.exceptions import ValidationError
from pkgpanda import PackageId
from pkgpanda.constants import (
    cloud_config_yaml,
    config_dir,
    dcos_config_yaml,
    dcos_services_yaml,
)
from pkgpanda.util import (
    hash_checkout,
    is_absolute_path,
    is_windows,
    json_prettyprint,
    load_string,
    split_by_token,
    write_json,
    write_string,
    write_yaml,
)

# List of all roles all templates should have.
role_names = {"master", "slave", "slave_public"}

role_template = config_dir + '/roles/{}'

if is_windows:
    CLOUDCONFIG_KEYS = {'runcmd', 'root', 'mounts', 'disk_setup', 'fs_setup', 'bootcmd'}
else:
    CLOUDCONFIG_KEYS = {'coreos', 'runcmd', 'apt_sources', 'root', 'mounts', 'disk_setup', 'fs_setup', 'bootcmd'}
PACKAGE_KEYS = {'package', 'root'}


# Allow overriding calculators with a `gen_extra/calc.py` if it exists
gen_extra_calc = None
if os.path.exists('gen_extra/calc.py'):
    gen_extra_calc = importlib.machinery.SourceFileLoader('gen_extra.calc', 'gen_extra/calc.py').load_module()


def validate_downstream_entry(entry: dict) -> None:
    """Raise an exception if entry is an invalid downstream gen.internals.Source entry."""
    version_key = 'dcos_version'
    entry_keys = set(entry.get('must', {}).keys()) | set(entry.get('default', {}).keys())
    if version_key in entry_keys:
        raise Exception(
            'The downstream entry redefines config param {}, which must be inherited from upstream'.format(version_key)
        )


def stringify_configuration(configuration: dict):
    """Create a stringified version of the complete installer configuration
    to send to gen.generate()"""
    gen_config = {}
    for key, value in configuration.items():
        if isinstance(value, list) or isinstance(value, dict):
            log.debug("Caught %s for genconf configuration, transforming to JSON string: %s", type(value), value)
            value = json.dumps(value)

        elif isinstance(value, bool):
            if value:
                value = 'true'
            else:
                value = 'false'

        elif isinstance(value, int):
            log.debug("Caught int for genconf configuration, transforming to string: %s", value)
            value = str(value)

        elif isinstance(value, str):
            pass

        else:
            log.error("Invalid type for value of %s in config. Got %s, only can handle list, dict, "
                      "int, bool, and str", key, type(value))
            raise Exception()

        gen_config[key] = value

    log.debug('Stringified configuration: \n{}'.format(gen_config))
    return gen_config


def add_roles(cloudconfig, roles):
    for role in roles:
        cloudconfig['write_files'].append({
            "path": role_template.format(role),
            "content": ""})

    return cloudconfig


def add_units(cloudconfig, services, cloud_init_implementation='coreos'):
    '''
    Takes a services dict in the format of CoreOS cloud-init 'units' and
    injects into cloudconfig a transformed version appropriate for the
    cloud_init_implementation.  See:
    https://coreos.com/os/docs/latest/cloud-config.html for the CoreOS 'units'
    specification. See: https://cloudinit.readthedocs.io/en/latest/index.html
    for the Canonical implementation.

    Parameters:
    * cloudconfig is a dict
    * services is a list of dict's
    * cloud_init_implementation is a string: 'coreos' or 'canonical'
    '''
    if cloud_init_implementation == 'canonical':
        cloudconfig.setdefault('write_files', [])
        cloudconfig.setdefault('runcmd', [])
        for unit in services:
            unit_name = unit['name']
            if 'content' in unit:
                write_files_entry = {'path': '/etc/systemd/system/{}'.format(unit_name),
                                     'content': unit['content'],
                                     'permissions': '0644'}
                cloudconfig['write_files'].append(write_files_entry)
            if 'enable' in unit and unit['enable']:
                runcmd_entry = ['systemctl', 'enable', unit_name]
                cloudconfig['runcmd'].append(runcmd_entry)
            if 'command' in unit:
                opts = []
                if 'no_block' in unit and unit['no_block']:
                    opts.append('--no-block')
                if unit['command'] in ['start', 'stop', 'reload', 'restart', 'try-restart', 'reload-or-restart',
                                       'reload-or-try-restart']:
                    runcmd_entry = ['systemctl'] + opts + [unit['command'], unit_name]
                else:
                    raise Exception("Unsupported unit command: {}".format(unit['command']))
                cloudconfig['runcmd'].append(runcmd_entry)
    elif cloud_init_implementation == 'coreos':
        cloudconfig.setdefault('coreos', {}).setdefault('units', [])
        cloudconfig['coreos']['units'] += services
    else:
        raise Exception("Parameter value '{}' is invalid for cloud_init_implementation".format(
            cloud_init_implementation))

    return cloudconfig


# For converting util -> a namespace only.
class Bunch(object):

    def __init__(self, adict):
        self.__dict__.update(adict)


def render_cloudconfig(data):
    return "#cloud-config\n" + render_yaml(data)


utils = Bunch({
    "role_template": role_template,
    "add_roles": add_roles,
    "role_names": role_names,
    "add_services": None,
    "add_stable_artifact": None,
    "add_channel_artifact": None,
    "add_units": add_units,
    "render_cloudconfig": render_cloudconfig
})


def render_yaml(data):
    return yaml.dump(data, default_style='|', default_flow_style=False)


# Recursively merge to python dictionaries.
# If both base and addition contain the same key, that key's value will be
# merged if it is a dictionary.
# This is unlike the python dict.update() method which just overwrites matching
# keys.
def merge_dictionaries(base, additions):
    base_copy = base.copy()
    for k, v in additions.items():
        try:
            if k not in base:
                base_copy[k] = v
                continue
            if isinstance(v, dict) and isinstance(base_copy[k], dict):
                base_copy[k] = merge_dictionaries(base_copy.get(k, dict()), v)
                continue

            # Append arrays
            if isinstance(v, list) and isinstance(base_copy[k], list):
                base_copy[k].extend(v)
                continue

            # Merge sets
            if isinstance(v, set) and isinstance(base_copy[k], set):
                base_copy[k] |= v
                continue

            # Unknown types
            raise ValueError("Can't merge type {} into type {}".format(type(v), type(base_copy[k])))
        except ValueError as ex:
            raise ValueError("{} inside key {}".format(ex, k)) from ex
    return base_copy


def load_templates(template_dict):
    result = dict()
    for name, template_list in template_dict.items():
        result_list = list()
        for template_name in template_list:
            result_list.append(gen.template.parse_resources(template_name))

            extra_filename = "gen_extra/" + template_name
            if os.path.exists(extra_filename):
                result_list.append(gen.template.parse_str(
                    load_string(extra_filename)))
        result[name] = result_list
    return result


# Render the Jinja/YAML into YAML, then load the YAML and merge it to make the
# final configuration files.
def render_templates(template_dict, arguments):
    rendered_templates = dict()
    templates = load_templates(template_dict)
    for name, templates in templates.items():
        full_template = None
        for template in templates:
            rendered_template = template.render(arguments)

            # If not yaml, just treat opaquely.
            if not name.endswith('.yaml'):
                # No merging support currently.
                assert len(templates) == 1
                full_template = rendered_template
                continue
            template_data = yaml.safe_load(rendered_template)

            if full_template:
                full_template = merge_dictionaries(full_template, template_data)
            else:
                full_template = template_data

        rendered_templates[name] = full_template

    return rendered_templates


# Collect the un-bound / un-set variables from all the given templates to build
# the schema / configuration target. The templates and their structure serve
# as the schema for what configuration a user must provide.
def target_from_templates(template_dict):
    # NOTE: the individual yaml template targets are merged into one target
    # since we never want to target just one template at a time for now (they
    # all merge into one config package).
    target = gen.internals.Target()
    templates = load_templates(template_dict)
    for template_list in templates.values():
        for template in template_list:
            target += template.target_from_ast()

    return [target]


def write_to_non_taken(base_filename, json):
    number = 0

    filename = base_filename
    while (os.path.exists(filename)):
        number += 1
        filename = base_filename + '.{}'.format(number)

    write_json(filename, json)

    return filename


def do_gen_package(config, package_filename):
    # Generate the specific dcos-config package.
    # Version will be setup-{sha1 of contents}
    with gen.util.pkgpanda_package_tmpdir() as tmpdir:
        # Only contains package, root
        assert config.keys() == {"package"}

        # Write out the individual files
        for file_info in config["package"]:
            assert file_info.keys() <= {"path", "content", "permissions"}
            if is_absolute_path(file_info['path']):
                fileinfo_drive, fileinfo_path = os.path.splitdrive(file_info['path'])
                path = tmpdir + fileinfo_path
            else:
                path = tmpdir + '/' + file_info['path']
            try:
                if os.path.dirname(path):
                    os.makedirs(os.path.dirname(path), mode=0o755)
            except FileExistsError:
                pass

            with open(path, 'w') as f:
                f.write(file_info['content'] or '')

            # the file has special mode defined, handle that.
            if 'permissions' in file_info:
                assert isinstance(file_info['permissions'], str)
                os.chmod(path, int(file_info['permissions'], 8))
            else:
                os.chmod(path, 0o644)

        gen.util.make_pkgpanda_package(tmpdir, package_filename)


def render_late_content(content, late_values):

    def _dereference_placeholders(parts):
        for part, is_placeholder in parts:
            if is_placeholder:
                if part not in late_values:
                    log.debug('Found placeholder for unknown value "{}" in late config: {}'.format(part, repr(content)))
                    raise Exception('Bad late config file: Found placeholder for unknown value "{}"'.format(part))
                yield late_values[part]
            else:
                yield part

    return ''.join(_dereference_placeholders(split_by_token(
        gen.internals.LATE_BIND_PLACEHOLDER_START,
        gen.internals.LATE_BIND_PLACEHOLDER_END,
        content,
        strip_token_decoration=True,
    )))


def _late_bind_placeholder_in(string_):
    return gen.internals.LATE_BIND_PLACEHOLDER_START in string_ or gen.internals.LATE_BIND_PLACEHOLDER_END in string_


def resolve_late_package(config, late_values):
    resolved_config = {
        'package': [
            {k: render_late_content(v, late_values) if k == 'content' else v for k, v in file_info.items()}
            for file_info in config['package']
        ]
    }

    assert not any(
        _late_bind_placeholder_in(v) for file_info in resolved_config['package'] for v in file_info.values()
    ), 'Resolved late package must not contain late value placeholder: {}'.format(resolved_config)

    return resolved_config


def extract_files_containing_late_variables(start_files):
    found_files = []
    left_files = []

    for file_info in deepcopy(start_files):
        assert not any(_late_bind_placeholder_in(v) for k, v in file_info.items() if k != 'content'), (
            'File info must not contain late config placeholder in fields other than content: {}'.format(file_info)
        )

        if file_info['content'] and _late_bind_placeholder_in(file_info['content']):
            found_files.append(file_info)
        else:
            left_files.append(file_info)

    # All files still belong somewhere
    assert len(found_files) + len(left_files) == len(start_files)

    return found_files, left_files


# Validate all arguments passed in actually correspond to parameters to
# prevent human typo errors.
# This includes all possible sub scopes (Including config for things you don't use is fine).
def flatten_parameters(scoped_parameters):
    flat = copy(scoped_parameters.get('variables', set()))
    for name, possible_values in scoped_parameters.get('sub_scopes', dict()).items():
        flat.add(name)
        for sub_scope in possible_values.values():
            flat |= flatten_parameters(sub_scope)

    return flat


def validate_all_arguments_match_parameters(parameters, setters, arguments):
    errors = dict()

    # Gather all possible parameters from templates as well as setter parameters.
    all_parameters = flatten_parameters(parameters)
    for setter_list in setters.values():
        for setter in setter_list:
            all_parameters |= setter.parameters
            all_parameters.add(setter.name)
            all_parameters |= {name for name, value in setter.conditions}

    # Check every argument is in the set of parameters.
    for argument in arguments:
        if argument not in all_parameters:
            errors[argument] = 'Argument {} given but not in possible parameters {}'.format(argument, all_parameters)

    if len(errors):
        raise ValidationError(errors, set())


def validate(
        arguments,
        extra_templates=list(),
        extra_sources=list()):
    sources, targets, _ = get_dcosconfig_source_target_and_templates(arguments, extra_templates, extra_sources)
    return gen.internals.resolve_configuration(sources, targets).status_dict


def user_arguments_to_source(user_arguments) -> gen.internals.Source:
    """Convert all user arguments to be a gen.internals.Source"""

    # Make sure all user provided arguments are strings.
    # TODO(cmaloney): Loosen this restriction  / allow arbitrary types as long
    # as they all have a gen specific string form.
    gen.internals.validate_arguments_strings(user_arguments)

    user_source = gen.internals.Source(is_user=True)
    for name, value in user_arguments.items():
        user_source.add_must(name, value)
    return user_source


# TODO(cmaloney): This function should disolve away like the ssh one is and just become a big
# static dictonary or pass in / construct on the fly at the various template callsites.
def get_dcosconfig_source_target_and_templates(
        user_arguments: dict,
        extra_templates: List[str],
        extra_sources: List[gen.internals.Source]):
    log.info("Generating configuration files...")

    # TODO(cmaloney): Make these all just defined by the base calc.py
    # There are separate configuration files for windows vs non-windows as a lot
    # of configuration on windows will be different.
    if is_windows:
        config_package_names = ['dcos-config-windows', 'dcos-metadata']
    else:
        config_package_names = ['dcos-config', 'dcos-metadata']

    template_filenames = [dcos_config_yaml, cloud_config_yaml, 'dcos-metadata.yaml', dcos_services_yaml]

    # TODO(cmaloney): Check there are no duplicates between templates and extra_template_files
    template_filenames += extra_templates

    # Re-arrange templates to be indexed by common name. Only allow multiple for one key if the key
    # is yaml (ends in .yaml).
    templates = dict()
    for filename in template_filenames:
        key = os.path.basename(filename)
        templates.setdefault(key, list())
        templates[key].append(filename)

        if len(templates[key]) > 1 and not key.endswith('.yaml'):
            raise Exception(
                "Internal Error: Only know how to merge YAML templates at this point in time. "
                "Can't merge template {} in template_list {}".format(filename, templates[key]))

    targets = target_from_templates(templates)
    base_source = gen.internals.Source(is_user=False)
    base_source.add_entry(gen.calc.entry, replace_existing=False)

    if gen_extra_calc:
        validate_downstream_entry(gen_extra_calc.entry)
        base_source.add_entry(gen_extra_calc.entry, replace_existing=True)

    def add_builtin(name, value):
        base_source.add_must(name, json_prettyprint(value))

    sources = [base_source, user_arguments_to_source(user_arguments)] + extra_sources

    # Add builtin variables.
    # TODO(cmaloney): Hash the contents of all the templates rather than using the list of filenames
    # since the filenames might not live in this git repo, or may be locally modified.
    add_builtin('template_filenames', template_filenames)
    add_builtin('config_package_names', list(config_package_names))

    # Add placeholders for builtin variables whose values will be calculated after all others, so that we won't get
    # unset argument errors. The placeholder value with be replaced with the actual value after all other variables are
    # calculated.
    temporary_str = 'DO NOT USE THIS AS AN ARGUMENT TO OTHER ARGUMENTS. IT IS TEMPORARY'
    add_builtin('user_arguments_full', temporary_str)
    add_builtin('user_arguments', temporary_str)
    add_builtin('config_yaml_full', temporary_str)
    add_builtin('config_yaml', temporary_str)
    add_builtin('expanded_config', temporary_str)
    add_builtin('expanded_config_full', temporary_str)

    # Note: must come last so the hash of the "base_source" this is beign added to contains all the
    # variables but this.
    add_builtin('sources_id', hash_checkout([hash_checkout(source.make_id()) for source in sources]))

    return sources, targets, templates


def build_late_package(late_files, config_id, provider):
    if not late_files:
        return None

    # Add a empty pkginfo.json to the late package after validating there
    # isn't already one.
    for file_info in late_files:
        assert file_info['path'] != '/pkginfo.json'
        assert is_absolute_path(file_info['path'])

    late_files.append({
        "path": "/pkginfo.json",
        "content": "{}"})

    return {
        'package': late_files,
        'name': 'dcos-provider-{}-{}--setup'.format(config_id, provider)
    }


def validate_and_raise(sources, targets):
    # TODO(cmaloney): Make it so we only get out the dcosconfig target arguments not all the config target arguments.
    resolver = gen.internals.resolve_configuration(sources, targets)
    status = resolver.status_dict

    if status['status'] == 'errors':
        raise ValidationError(errors=status['errors'], unset=status['unset'])

    return resolver


def get_late_variables(resolver, sources):
    # Gather out the late variables. The presence of late variables changes
    # whether or not a late package is created
    late_variables = dict()
    # TODO(branden): Get the late vars and expressions from resolver.late
    for source in sources:
        for setter_list in source.setters.values():
            for setter in setter_list:
                if not setter.is_late:
                    continue

                if setter.name not in resolver.late:
                    continue

                # Skip late vars that aren't referenced by config.
                if not resolver.arguments[setter.name].is_finalized:
                    continue

                # Validate a late variable should only have one source.
                assert setter.name not in late_variables

                late_variables[setter.name] = setter.late_expression
    log.debug('Late variables:\n{}'.format(pprint.pformat(late_variables)))

    return late_variables


def get_secret_variables(sources):
    return list(set(var_name for source in sources for var_name in source.secret))


def get_final_arguments(resolver):
    return {k: v.value for k, v in resolver.arguments.items() if v.is_finalized}


def format_expanded_config(config):
    return textwrap.indent(json_prettyprint(config), prefix=('  ' * 3))


def user_arguments_to_yaml(user_arguments: dict):
    return textwrap.indent(
        yaml.dump(user_arguments, default_style='|', default_flow_style=False, indent=2),
        prefix=('  ' * 3),
    )


def generate(
        arguments,
        extra_templates=list(),
        extra_sources=list(),
        extra_targets=list()):
    # To maintain the old API where we passed arguments rather than the new name.
    user_arguments = arguments
    arguments = None

    sources, targets, templates = get_dcosconfig_source_target_and_templates(
        user_arguments, extra_templates, extra_sources)

    resolver = validate_and_raise(sources, targets + extra_targets)
    argument_dict = get_final_arguments(resolver)
    late_variables = get_late_variables(resolver, sources)
    secret_builtins = ['expanded_config_full', 'user_arguments_full', 'config_yaml_full']
    secret_variables = set(get_secret_variables(sources) + secret_builtins)
    masked_value = '**HIDDEN**'

    # Calculate values for builtin variables.
    user_arguments_masked = {k: (masked_value if k in secret_variables else v) for k, v in user_arguments.items()}
    argument_dict['user_arguments_full'] = json_prettyprint(user_arguments)
    argument_dict['user_arguments'] = json_prettyprint(user_arguments_masked)
    argument_dict['config_yaml_full'] = user_arguments_to_yaml(user_arguments)
    argument_dict['config_yaml'] = user_arguments_to_yaml(user_arguments_masked)

    # The expanded_config and expanded_config_full variables contain all other variables and their values.
    # expanded_config is a copy of expanded_config_full with secret values removed. Calculating these variables' values
    # must come after the calculation of all other variables to prevent infinite recursion.
    # TODO(cmaloney): Make this late-bound by gen.internals
    expanded_config_full = {
        k: v for k, v in argument_dict.items()
        # Omit late-bound variables whose values have not yet been calculated.
        if not v.startswith(gen.internals.LATE_BIND_PLACEHOLDER_START)
    }
    expanded_config_scrubbed = {k: v for k, v in expanded_config_full.items() if k not in secret_variables}
    argument_dict['expanded_config_full'] = format_expanded_config(expanded_config_full)
    argument_dict['expanded_config'] = format_expanded_config(expanded_config_scrubbed)

    log.debug(
        "Final arguments:" + json_prettyprint({
            # Mask secret config values.
            k: (masked_value if k in secret_variables else v) for k, v in argument_dict.items()
        })
    )

    # Fill in the template parameters
    # TODO(cmaloney): render_templates should ideally take the template targets.
    rendered_templates = render_templates(templates, argument_dict)

    # Validate there aren't any unexpected top level directives in any of the files
    # (likely indicates a misspelling)
    for name, template in rendered_templates.items():
        if name == dcos_services_yaml:  # yaml list of the service files
            assert isinstance(template, list)
        elif name == cloud_config_yaml:
            assert template.keys() <= CLOUDCONFIG_KEYS, template.keys()
        elif isinstance(template, str):  # Not a yaml template
            pass
        else:  # yaml template file
            log.debug("validating template file %s", name)
            assert template.keys() <= PACKAGE_KEYS, template.keys()

    stable_artifacts = []
    channel_artifacts = []

    # Find all files which contain late bind variables and turn them into a "late bind package"
    # TODO(cmaloney): check there are no late bound variables in cloud-config.yaml
    late_files, regular_files = extract_files_containing_late_variables(
        rendered_templates[dcos_config_yaml]['package'])
    # put the regular files right back
    rendered_templates[dcos_config_yaml] = {'package': regular_files}

    # Render cluster package list artifact.
    cluster_package_list_filename = 'package_lists/{}.package_list.json'.format(
        argument_dict['cluster_package_list_id']
    )
    os.makedirs(os.path.dirname(cluster_package_list_filename), mode=0o755, exist_ok=True)
    write_string(cluster_package_list_filename, argument_dict['cluster_packages'])
    log.info('Cluster package list: {}'.format(cluster_package_list_filename))
    stable_artifacts.append(cluster_package_list_filename)

    def make_package_filename(package_id, extension):
        return 'packages/{0}/{1}{2}'.format(
            package_id.name,
            repr(package_id),
            extension)

    # Render all the cluster packages
    cluster_package_info = {}

    # Prepare late binding config, if any.
    late_package = build_late_package(late_files, argument_dict['config_id'], argument_dict['provider'])
    if late_variables and late_package:
        # Render the late binding package. This package will be downloaded onto
        # each cluster node during bootstrap and rendered into the final config
        # using the values from the late config file.
        late_package_id = PackageId(late_package['name'])
        late_package_filename = make_package_filename(late_package_id, '.dcos_config')
        os.makedirs(os.path.dirname(late_package_filename), mode=0o755)
        write_yaml(late_package_filename, {'package': late_package['package']}, default_flow_style=False)
        log.info('Package filename: {}'.format(late_package_filename))
        stable_artifacts.append(late_package_filename)

        # Add the late config file to cloud config. The expressions in
        # late_variables will be resolved by the service handling the cloud
        # config (e.g. Amazon CloudFormation). The rendered late config file
        # on a cluster node's filesystem will contain the final values.
        rendered_templates[cloud_config_yaml]['root'].append({
            'path': config_dir + '/setup-flags/late-config.yaml',
            'permissions': '0644',
            'owner': 'root',
            # TODO(cmaloney): don't prettyprint to save bytes.
            # NOTE: Use yaml here simply to make avoiding painful escaping and
            # unescaping easier.
            'content': render_yaml({
                'late_bound_package_id': late_package['name'],
                'bound_values': late_variables
            })})

    # Collect metadata for cluster packages.
    for package_id_str in json.loads(argument_dict['cluster_packages']):
        package_id = PackageId(package_id_str)
        package_filename = make_package_filename(package_id, '.tar.xz')

        cluster_package_info[package_id.name] = {
            'id': package_id_str,
            'filename': package_filename
        }

    # Render config packages.
    config_package_ids = json.loads(argument_dict['config_package_ids'])
    for package_id_str in config_package_ids:
        package_id = PackageId(package_id_str)
        package_filename = cluster_package_info[package_id.name]['filename']
        do_gen_package(rendered_templates[package_id.name + '.yaml'], cluster_package_info[package_id.name]['filename'])
        stable_artifacts.append(package_filename)

    # Convert cloud-config to just contain write_files rather than root
    cc = rendered_templates[cloud_config_yaml]

    # Shouldn't contain any packages. Providers should pull what they need to
    # late bind out of other packages via cc_package_file.
    assert 'package' not in cc
    cc_root = cc.pop('root', [])
    # Make sure write_files exists.
    assert 'write_files' not in cc
    cc['write_files'] = []
    # Do the transform
    for item in cc_root:
        assert is_absolute_path(item['path'])
        cc['write_files'].append(item)
    rendered_templates[cloud_config_yaml] = cc

    # Add utils that need to be defined here so they can be bound to locals.
    def add_services(cloudconfig, cloud_init_implementation):
        return add_units(cloudconfig, rendered_templates[dcos_services_yaml], cloud_init_implementation)

    utils.add_services = add_services

    def add_stable_artifact(filename):
        assert filename not in stable_artifacts + channel_artifacts
        stable_artifacts.append(filename)

    utils.add_stable_artifact = add_stable_artifact

    def add_channel_artifact(filename):
        assert filename not in stable_artifacts + channel_artifacts
        channel_artifacts.append(filename)

    utils.add_channel_artifact = add_channel_artifact

    return Bunch({
        'arguments': argument_dict,
        'cluster_packages': cluster_package_info,
        'stable_artifacts': stable_artifacts,
        'channel_artifacts': channel_artifacts,
        'templates': rendered_templates,
        'utils': utils
    })
