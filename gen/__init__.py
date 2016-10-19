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
import inspect
import json
import logging as log
import os
import os.path
import textwrap
from copy import copy, deepcopy
from functools import partialmethod
from tempfile import TemporaryDirectory

import yaml

import gen.calc
import gen.template
from pkgpanda import PackageId
from pkgpanda.util import load_string, make_tar

# List of all roles all templates should have.
role_names = {"master", "slave", "slave_public"}

role_template = '/etc/mesosphere/roles/{}'

CLOUDCONFIG_KEYS = {'coreos', 'runcmd', 'apt_sources', 'root', 'mounts', 'disk_setup', 'fs_setup', 'bootcmd'}
PACKAGE_KEYS = {'package', 'root'}


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


# Recursively merge to python dictionaries.
# If both base and addition contain the same key, that key's value will be
# merged if it is a dictionary.
# This is unlike the python dict.update() method which just overwrites matching
# keys.
def merge_replace_append_dictionaries(base, additions):
    base_copy = base.copy()
    for k, v in additions.items():
        try:
            if k not in base:
                base_copy[k] = v
                continue
            if isinstance(v, dict) and isinstance(base_copy[k], dict):
                base_copy[k] = merge_replace_append_dictionaries(base_copy.get(k, dict()), v)
                continue

            # Append arrays
            if isinstance(v, list) and isinstance(base_copy[k], list):
                base_copy[k].extend(v)
                continue

            # Merge sets
            if isinstance(v, set) and isinstance(base_copy[k], set):
                base_copy[k] |= v
                continue

            # Overwrite if the new one is a string
            if isinstance(v, str):
                base_copy[k] = v
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
            template_data = yaml.load(rendered_template)

            if full_template:
                full_template = merge_dictionaries(full_template, template_data)
            else:
                full_template = template_data

        rendered_templates[name] = full_template

    return rendered_templates


# Load all the un-bound variables in the templates which need to be given values
# in order to convert the templates to go from jinja -> final template. These
# are effectively the set of DC/OS parameters.
def get_parameters(template_dict):
    parameters = {'variables': set(), 'sub_scopes': dict()}
    templates = load_templates(template_dict)
    for template_list in templates.values():
        for template in template_list:
            parameters = merge_dictionaries(parameters, template.get_scoped_arguments())

    return parameters


def get_function_parameters(function):
    return set(inspect.signature(function).parameters)


class CalculatorError(Exception):
    def __init__(self, message, chain=[]):
        assert isinstance(message, str)
        assert isinstance(chain, list)
        self.message = message
        self.chain = chain
        super().__init__(message)


# Depth first search argument calculator. Detects cycles, as well as unmet
# dependencies.
# TODO(cmaloney): Separate chain / path building when unwinding from the root
#                 error messages.
class DFSArgumentCalculator():
    def __init__(self, setters, validate_fns):
        self._setters = setters
        self._arguments = dict()
        self.__in_progress = set()
        self._errors = dict()
        self._unset = set()

        # Re-arrange the validation functions so we can more easily access them by
        # argument name.
        self._validate_by_arg = dict()
        self._multi_arg_validate = dict()

        for fn in validate_fns:
            parameters = get_function_parameters(fn)
            # Could build up the single and multi parameter validation function maps in the same
            # thing but the timing / handling of when and how we run single vs. multi-parameter
            # validation functions is fairly different, the extra bit here simplifies the later code.
            if len(parameters) == 1:
                self._validate_by_arg[parameters.pop()] = fn
                assert not parameters
            else:
                self._multi_arg_validate[frozenset(parameters)] = fn

    def _calculate_argument(self, name):
        # Filter out any setters which have predicates / conditions which are
        # satisfiably false.
        def all_conditions_met(setter):
            for condition_name, condition_value in setter.conditions:
                try:
                    if self._get(condition_name) != condition_value:
                        return False
                except CalculatorError as ex:
                    raise CalculatorError(
                        ex.message,
                        ex.chain + ['trying to test condition {}={}'.format(condition_name, condition_value)]) from ex
            return True

        # Find the right setter to calculate the argument.
        feasible = list(filter(all_conditions_met, self._setters.get(name, list())))

        if len(feasible) == 0:
            self._unset.add(name)
            raise CalculatorError("no way to set")

        # Filtier out all optional setters if there is more than one way to set.
        if len(feasible) > 1:
            final_feasible = list(filter(lambda setter: not setter.is_optional, feasible))
            assert final_feasible, "Had multiple optionals and no musts. Template internal error: {!r}".format(feasible)
            feasible = final_feasible

        # Must be calculated but user tried to provide.
        if len(feasible) == 2 and (feasible[0].is_user or feasible[1].is_user):
            self._errors[name] = ("{} must be calculated, but was explicitly set in the "
                                  "configuration. Remove it from the configuration.").format(name)
            raise CalculatorError("{} must be calculated but set twice".format(name))

        if len(feasible) > 1:
            self._errors[name] = "Internal error: Multiple ways to set {}.".format(name)
            raise CalculatorError("multiple ways to set",
                                  ["options: {}".format(feasible)])

        setter = feasible[0]

        # Get values for the parameters, then call. the setter function.
        kwargs = {}
        for parameter in setter.parameters:
            kwargs[parameter] = self._get(parameter)

        try:
            value = setter.calc(**kwargs)
        except AssertionError as ex:
            self._errors[name] = ex.args[0]
            raise CalculatorError("assertion while calc")

        if name in self._validate_by_arg:
            try:
                self._validate_by_arg[name](value)
            except AssertionError as ex:
                self._errors[name] = ex.args[0]
                raise CalculatorError("assertion while validate")

        return value

    def _get(self, name):
        if name in self._arguments:
            if self._arguments[name] is None:
                raise CalculatorError("No way to set", [name])
            return self._arguments[name]

        # Detect cycles by checking if we're in the middle of calculating the
        # argument being asked for
        if name in self.__in_progress:
            raise CalculatorError("Internal error. cycle detected. re-encountered {}".format(name))

        self.__in_progress.add(name)
        try:
            self._arguments[name] = self._calculate_argument(name)
            return self._arguments[name]
        except CalculatorError as ex:
            self._arguments[name] = None
            raise CalculatorError(ex.message, ex.chain + ['while calculating {}'.format(name)]) from ex
        except:
            self._arguments[name] = None
            raise
        finally:
            self.__in_progress.remove(name)

    # Force calculation of all arguments by accessing the arguments in this
    # scope and recursively all sub-scopes.
    def calculate(self, scope, throw_on_error=True):
        def evaluate_var(name):
            try:
                self._get(name)
            except CalculatorError as ex:
                log.debug("Error calculating %s: %s. Chain: %s", name, ex.message, ex.chain)

        assert scope.keys() <= {'sub_scopes', 'variables'}, \
            "scope should only have variables and sub_scopes. Found: {}".format(scope)

        for name in scope.get('variables', set()):
            evaluate_var(name)

        for name, sub_scope in scope.get('sub_scopes', dict()).items():
            if name not in self._arguments:
                evaluate_var(name)

            # If the internal arg is None, there was an error, don't check if it
            # is a legal choice.
            if self._arguments[name] is None:
                continue

            choice = self._get(name)

            if choice not in sub_scope:
                self._errors[name] = "Invalid choice {}. Must choose one of {}".format(
                    choice, ", ".join(sorted(sub_scope.keys())))
                continue

            self.calculate(sub_scope[choice], throw_on_error=False)

        # Perform all multi-argument validations
        for parameter_set, validate_fn in self._multi_arg_validate.items():
            # Build up argument map for validate function. If any arguments are
            # unset then skip this validate function.
            kwargs = dict()
            skip = False
            for parameter in parameter_set:
                if parameter not in self._arguments or self._arguments[parameter] is None:
                    skip = True
                    break
                kwargs[parameter] = self._arguments[parameter]
            if skip:
                continue

            # Call the validation function, catching AssertionErrors and turning them into errors in
            # the error dictionary.
            try:
                validate_fn(**kwargs)
            except AssertionError as ex:
                self._errors[parameter_set] = ex.args[0]

        if throw_on_error and (len(self._errors) or len(self._unset)):
            raise ValidationError(self._errors, self._unset)

        return self._arguments


json_prettyprint_args = {
    "sort_keys": True,
    "indent": 2,
    "separators": (',', ':')
}


def write_json(filename, data):
    with open(filename, "w+") as f:
        return json.dump(data, f, **json_prettyprint_args)


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
    # Forcibly set umask so that os.makedirs() always makes directories with
    # uniform permissions
    os.umask(0o000)

    with TemporaryDirectory("gen_tmp_pkg") as tmpdir:

        # Only contains package, root
        assert config.keys() == {"package"}

        # Write out the individual files
        for file_info in config["package"]:
            assert file_info.keys() <= {"path", "content", "permissions"}
            if file_info['path'].startswith('/'):
                path = tmpdir + file_info['path']
            else:
                path = tmpdir + '/' + file_info['path']
            try:
                if os.path.dirname(path):
                    os.makedirs(os.path.dirname(path), mode=0o755)
            except FileExistsError:
                pass

            with open(path, 'w') as f:
                f.write(file_info['content'])

            # the file has special mode defined, handle that.
            if 'permissions' in file_info:
                assert isinstance(file_info['permissions'], str)
                os.chmod(path, int(file_info['permissions'], 8))
            else:
                os.chmod(path, 0o644)

        # Ensure the output directory exists
        if os.path.dirname(package_filename):
            os.makedirs(os.path.dirname(package_filename), exist_ok=True)

        # Make the package top level directory readable by users other than the owner (root).
        os.chmod(tmpdir, 0o755)

        make_tar(package_filename, tmpdir)

    log.info("Package filename: %s", package_filename)


def validate_arguments_strings(arguments: dict):
    errors = dict()
    # Validate that all keys and vlaues of arguments are strings
    for k, v in arguments.items():
        if not isinstance(k, str):
            errors[''] = "All keys in arguments must be strings. '{}' isn't.".format(k)
        if not isinstance(v, str):
            errors[k] = ("All values in arguments must be strings. Value for argument {} isn't. " +
                         "Given value: {}").format(k, v)
    if len(errors):
        raise ValidationError(errors, set())


def extract_files_with_path(start_files, paths):
    found_files = []
    found_file_paths = []
    left_files = []

    for file_info in deepcopy(start_files):
        if file_info['path'] in paths:
            found_file_paths.append(file_info['path'])
            found_files.append(file_info)
        else:
            left_files.append(file_info)

    # Assert all files were found. If not it was a programmer error of some form.
    assert set(found_file_paths) == set(paths)
    # All files still belong somewhere
    assert len(found_files) + len(left_files) == len(start_files)

    return found_files, left_files


class Setter():
    # NOTE: value may either be a function or a string.
    def __init__(self, name, value, is_optional, conditions, is_user):
        assert isinstance(conditions, list)
        self.name = name
        self.is_optional = is_optional
        self.conditions = conditions
        self.is_user = is_user

        def get_value():
            return value

        if isinstance(value, str):
            self.calc = get_value
            self.parameters = set()
        else:
            assert callable(value), "{} should be a string or callable. Got: {}".format(name, value)
            self.calc = value
            self.parameters = get_function_parameters(value)

    def __repr__(self):
        return "<Setter {}{}{}, conditions: {}{}>".format(
            self.name,
            ", optional" if self.is_optional else "",
            ", user" if self.is_user else "",
            self.conditions,
            ", parameters {}".format(self.parameters))


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


class ValidationError(Exception):
    def __init__(self, errors, unset):
        self.errors = errors
        self.unset = unset
        super().__init__(str(errors), str(unset))

    def __str__(self):
        return "<ValidationError errors: {}; unset: {}".format(self.errors, self.unset)

    def __repr__(self):
        return "<ValidationError errors: {}; unset: {}".format(self.errors, self.unset)


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


class ConfigTarget():
    def __init__(self, mandatory_parameters):
        self.validate = list()
        self.setters = dict()
        self.mandatory_parameters = mandatory_parameters

    def add_setter(self, name, value, is_optional, conditions, is_user):
        self.setters.setdefault(name, list()).append(Setter(name, value, is_optional, conditions, is_user))

    add_must = partialmethod(add_setter, is_optional=False, conditions=[], is_user=False)

    def add_conditional_scope(self, scope, conditions):
        # TODO(cmaloney): 'defaults' are the same as 'can' and 'must' is identical to 'arguments' except
        # that one takes functions and one takes strings. Simplify to just 'can', 'must'.
        assert scope.keys() <= {'validate', 'default', 'must', 'conditional'}

        self.validate += scope.get('validate', list())

        for name, fn in scope.get('must', dict()).items():
            self.add_setter(name, fn, False, conditions, False)

        for name, fn in scope.get('default', dict()).items():
            self.add_setter(name, fn, True, conditions, False)

        for name, cond_options in scope.get('conditional', dict()).items():
            for value, sub_scope in cond_options.items():
                self.add_conditional_scope(sub_scope, conditions + [(name, value)])

    def remove_setters(self, scope):
        def del_setter(name):
            if name in self.setters:
                del self.setters[name]

        for name in scope.get('must', dict()).keys():
            del_setter(name)

        for name in scope.get('default', dict()).keys():
            del_setter(name)

        for name, cond_options in scope.get('conditional', dict()).items():
            if name in self.setters:
                raise NotImplementedError("Should conditional setters overwrite all setters?")

    def add_entry(self, entry, replace_existing):
        if replace_existing:
            self.remove_setters(entry)

        self.add_conditional_scope(entry, [])


def calculate_config_for_targets(config_targets, user_arguments):
    assert isinstance(config_targets, list)

    # Make sure all user provided arguments are strings.
    validate_arguments_strings(user_arguments)

    validate = list()
    setters = dict()
    mandatory_parameters = {'variables': set(), 'sub_scopes': dict()}

    # Merge all the config targets into one big group of setters for providing
    # to the calculator
    # TODO(cmaloney): The setter management / set code is very similar to that in ConfigTarget, they
    # could probably be joined.
    for target in config_targets:
        for name, setter_list in target.setters.items():
            setters.setdefault(name, list())
            setters[name] = setters[name] + setter_list
        validate = validate + target.validate

        # TODO(cmaloney): The building of mandatory_parameters is identical to how we build it up in
        # get_parameters()
        mandatory_parameters = merge_dictionaries(mandatory_parameters, target.mandatory_parameters)

    # TODO(cmaloney): Validate recursively that mandatory_parameters has the right keys and only the
    # right keys.
    assert mandatory_parameters.keys() == {'variables', 'sub_scopes'}

    # TODO(cmaloney): Re-enable this after sorting out how to have "optional" config targets which
    # add in extra "acceptable" parameters (SSH Config, AWS Advanced Template config, etc)
    # validate_all_arguments_match_parameters(mandatory_parameters, setters, user_arguments)

    # Add in all user arguments as setters.
    # Happens last so that they are never overwritten with replace_existing=True
    for name, value in user_arguments.items():
        setters.setdefault(name, list()).append(Setter(name, value, False, [], True))

    # Use setters to caluclate every required parameter
    arguments = DFSArgumentCalculator(setters, validate).calculate(mandatory_parameters)

    # Validate all new / calculated arguments are strings.
    validate_arguments_strings(arguments)

    log.info("Final arguments:" + json.dumps(arguments, **json_prettyprint_args))

    # TODO(cmaloney) Give each config target the values for all it's parameters that were hit as
    # well as any parameters that led to those parameters.
    return arguments


def validate_config_for_targets(config_targets, user_arguments):
    try:
        calculate_config_for_targets(config_targets, user_arguments)
        return {'status': 'ok'}
    except ValidationError as ex:
        messages = {}

        # Defer multi-key validation errors and noramlize them to be single-key
        # ones. The multi-key is always less important than the single-key
        # messages which is why single-key messages we never overwrite.
        # TODO(cmaloney): Teach the whole stack to be able to handle multi-key
        # validation errors.
        to_do = dict()
        for key, msg in ex.errors.items():
            if isinstance(key, frozenset):
                to_do[key] = msg
                continue

            assert isinstance(key, str)
            messages[key] = {'message': msg}

        for keys, msg in to_do.items():
            for name in keys:
                # Skip ones we already have one message for.
                if name in messages:
                    continue

                messages[name] = {'message': msg}

        return {
            'status': 'errors',
            'errors': messages,
            'unset': ex.unset
        }


def validate(
        arguments,
        extra_templates=list(),
        cc_package_files=list()):
    config_target, _ = get_dcosconfig_target_and_templates(arguments, extra_templates)
    return validate_config_for_targets([config_target], arguments)


def get_dcosconfig_target_and_templates(user_arguments, extra_templates: list):
    log.info("Generating configuration files...")

    # TODO(cmaloney): Make these all just defined by the base calc.py
    package_names = ['dcos-config', 'dcos-metadata']
    template_filenames = ['dcos-config.yaml', 'cloud-config.yaml', 'dcos-metadata.yaml', 'dcos-services.yaml']

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

    mandatory_parameters = get_parameters(templates)
    config_target = ConfigTarget(mandatory_parameters)

    config_target.add_entry(gen.calc.entry, replace_existing=False)

    # Allow overriding calculators with a `gen_extra/calc.py` if it exists
    if os.path.exists('gen_extra/calc.py'):
        mod = importlib.machinery.SourceFileLoader('gen_extra.calc', 'gen_extra/calc.py').load_module()
        config_target.add_entry(mod.entry, replace_existing=True)

    def add_builtin(name, value):
        config_target.add_must(name, json.dumps(value, **json_prettyprint_args))

    # TODO(cmaloney): Hash the contents of all the templates rather than using the list of filenames
    # since the filenames might not live in this git repo, or may be locally modified.
    add_builtin('template_filenames', template_filenames)
    add_builtin('package_names', list(package_names))
    add_builtin('user_arguments', user_arguments)

    # Add a builtin for expanded_config, so that we won't get unset argument errors. The temporary
    # value will get replaced with the set of all arguments once calculation is complete
    temporary_str = 'DO NOT USE THIS AS AN ARGUMENT TO OTHER ARGUMENTS. IT IS TEMPORARY'
    add_builtin('expanded_config', temporary_str)

    return config_target, templates


def generate(
        arguments,
        extra_templates=list(),
        cc_package_files=list()):
    # To maintain the old API where we passed arguments rather than the new name.
    user_arguments = arguments
    arguments = None

    config_target, templates = get_dcosconfig_target_and_templates(user_arguments, extra_templates)

    # TODO(cmaloney): Make it so we only get out the dcosconfig target arguments not all the config target arguments.
    arguments = calculate_config_for_targets([config_target], user_arguments)
    log.debug("Final arguments:" + json.dumps(arguments, **json_prettyprint_args))

    # expanded_config is a special result which contains all other arguments. It has to come after
    # the calculation of all the other arguments so it can be filled with everything which was
    # calculated. Can't be calculated because that would have an infinite recursion problem (the set
    # of all arguments would want to include itself).
    # Explicitly / manaully setup so that it'll fit where we want it.
    arguments['expanded_config'] = textwrap.indent(json.dumps(arguments, **json_prettyprint_args),
                                                   prefix='  ' * 3)

    # Fill in the template parameters
    rendered_templates = render_templates(templates, arguments)

    # Validate there aren't any unexpected top level directives in any of the files
    # (likely indicates a misspelling)
    for name, template in rendered_templates.items():
        if name == 'dcos-services.yaml':  # yaml list of the service files
            assert isinstance(template, list)
        elif name == 'cloud-config.yaml':
            assert template.keys() <= CLOUDCONFIG_KEYS, template.keys()
        elif isinstance(template, str):  # Not a yaml template
            pass
        else:  # yaml template file
            log.debug("validating template file %s", name)
            assert template.keys() <= PACKAGE_KEYS, template.keys()

    # Extract cc_package_files out of the dcos-config template and put them into
    # the cloud-config package.
    cc_package_files, dcos_config_files = extract_files_with_path(rendered_templates['dcos-config.yaml']['package'],
                                                                  cc_package_files)
    rendered_templates['dcos-config.yaml'] = {'package': dcos_config_files}

    # Add a empty pkginfo.json to the cc_package_files.
    # Also assert there isn't one already (can only write out a file once).
    for item in cc_package_files:
        assert item['path'] != '/pkginfo.json'

    # If there aren't any files for a cloud-config package don't make one start
    # existing adding a pkginfo.json
    if len(cc_package_files) > 0:
        cc_package_files.append({
            "path": "/pkginfo.json",
            "content": "{}"})

    for item in cc_package_files:
        assert item['path'].startswith('/')
        item['path'] = '/etc/mesosphere/setup-packages/dcos-provider-{}--setup'.format(
            arguments['provider']) + item['path']
        rendered_templates['cloud-config.yaml']['root'].append(item)

    cluster_package_info = {}

    # Render all the cluster packages
    for package_id_str in json.loads(arguments['cluster_packages']):
        package_id = PackageId(package_id_str)
        package_filename = 'packages/{}/{}.tar.xz'.format(
            package_id.name,
            package_id_str)

        # Build the package
        do_gen_package(rendered_templates[package_id.name + '.yaml'], package_filename)

        cluster_package_info[package_id.name] = {
            'id': package_id_str,
            'filename': package_filename
        }

    # Convert cloud-config to just contain write_files rather than root
    cc = rendered_templates['cloud-config.yaml']

    # Shouldn't contain any packages. Providers should pull what they need to
    # late bind out of other packages via cc_package_file.
    assert 'package' not in cc
    cc_root = cc.pop('root', [])
    # Make sure write_files exists.
    assert 'write_files' not in cc
    cc['write_files'] = []
    # Do the transform
    for item in cc_root:
        assert item['path'].startswith('/')
        cc['write_files'].append(item)
    rendered_templates['cloud-config.yaml'] = cc

    # Add in the add_services util. Done here instead of the initial
    # map since we need to bind in parameters
    def add_services(cloudconfig, cloud_init_implementation):
        return add_units(cloudconfig, rendered_templates['dcos-services.yaml'], cloud_init_implementation)

    utils.add_services = add_services

    return Bunch({
        'arguments': arguments,
        'cluster_packages': cluster_package_info,
        'templates': rendered_templates,
        'utils': utils
    })
