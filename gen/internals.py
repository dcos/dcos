import copy
import inspect
import logging
from functools import partialmethod

from gen.exceptions import ValidationError
from pkgpanda.util import json_prettyprint

log = logging.getLogger(__name__)


def get_function_parameters(function):
    return set(inspect.signature(function).parameters)


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


class Setter:

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


class Scope:
    def __init__(self, name: str, cases=None):
        self.name = name
        self.cases = cases if cases else dict()

    def add_case(self, value: str, target):
        assert isinstance(target, Target)
        self.cases[value] = target

    def __iadd__(self, other):
        assert isinstance(other, Scope), "Internal consistency error, expected Scope but got {}".format(type(other))

        # Must have the same name and same options in order to be merged (can't have a new
        # switch add new, unhandled cases to a switch already included / represented by this scope).
        assert self.name == other.name, "Internal consistency error: Trying to merge scopes with " \
            "different names: {} and {}".format(self.name, other.name)
        assert self.cases.keys() == other.cases.keys(), "Same name / switch variable introduced " \
            "with a different set of possible cases. name: {}. First options: {}, Second " \
            "options: {}".format(self.name, self.cases.keys(), other.cases.keys())

        # Merge the targets for the cases
        for name in self.cases:
            self.cases[name] += other.cases[name]

        return self

    def __eq__(self, other):
        assert isinstance(other, Scope)
        return self.name == other.name and self.cases == other.cases


class Target:

    # TODO(cmaloney): Make a better API for working with and managing sub scopes. The current
    # dictionary of dictionaries is really hard to use right.
    def __init__(self, variables=None, sub_scopes=None):
        self.variables = variables if variables else set()
        self.sub_scopes = sub_scopes if sub_scopes else dict()

    def add_variable(self, variable: str):
        self.variables.add(variable)

    def add_scope(self, scope: Scope):
        self.sub_scopes[scope.name] = scope

    def __iadd__(self, other):
        assert isinstance(other, Target), "Internal consistency error, expected Target but got {}".format(type(other))
        self.variables |= other.variables

        # Add all scopes from the other to this, merging all common sub scopes.
        for name, scope in other.sub_scopes.items():
            if name in self.sub_scopes:
                self.sub_scopes[name] += scope
            else:
                self.sub_scopes[name] = scope

        return self

    def __eq__(self, other):
        assert isinstance(other, Target)
        return self.variables == other.variables and self.sub_scopes == other.sub_scopes


class Source:
    def __init__(self, entry=None, is_user=False,):
        self.setters = dict()
        self.validate = list()
        self.is_user = is_user
        if entry:
            self.add_entry(entry, False)

    def add_setter(self, name, value, is_optional, conditions):
        self.setters.setdefault(name, list()).append(Setter(name, value, is_optional, conditions, self.is_user))

    def add_conditional_scope(self, scope, conditions):
        # TODO(cmaloney): 'defaults' are the same as 'can' and 'must' is identical to 'arguments' except
        # that one takes functions and one takes strings. Simplify to just 'can', 'must'.
        assert scope.keys() <= {'validate', 'default', 'must', 'conditional'}

        self.validate += scope.get('validate', list())

        for name, fn in scope.get('must', dict()).items():
            self.add_setter(name, fn, False, conditions)

        for name, fn in scope.get('default', dict()).items():
            self.add_setter(name, fn, True, conditions)

        for name, cond_options in scope.get('conditional', dict()).items():
            for value, sub_scope in cond_options.items():
                self.add_conditional_scope(sub_scope, conditions + [(name, value)])

    add_must = partialmethod(add_setter, is_optional=False, conditions=[])

    def add_value_dict(self, value_dict):
        for name, value in value_dict.items():
            self.add_must(name, value)

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


# NOTE: This exception should never escape the DFSArgumentCalculator
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

    def _calculate_target(self, target):
        def evaluate_var(name):
            try:
                self._get(name)
            except CalculatorError as ex:
                log.debug("Error calculating %s: %s. Chain: %s", name, ex.message, ex.chain)

        for name in target.variables:
            evaluate_var(name)

        for name, sub_scope in target.sub_scopes.items():
            if name not in self._arguments:
                evaluate_var(name)

            # If the internal arg is None, there was an error, don't check if it
            # is a legal choice.
            if self._arguments[name] is None:
                continue

            choice = self._get(name)

            if choice not in sub_scope.cases:
                self._errors[name] = "Invalid choice {}. Must choose one of {}".format(
                    choice, ", ".join(sorted(sub_scope.keys())))
                continue

            self._calculate_target(sub_scope.cases[choice])

        # Perform all multi-argument validations
        for parameter_set, validate_fn in self._multi_arg_validate.items():
            # Build up argument map for validate function. If any arguments are
            # unset then skip this validate function.
            kwargs = dict()
            skip = False
            for parameter in parameter_set:
                if (parameter not in self._arguments) or (self._arguments[parameter] is None):
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

        # TODO(cmaloney): Return per-target results with the path to calculate each argument and the
        # full set of arguments touched included.
        return self._arguments

    # Force calculation of all arguments by accessing the arguments in this
    # scope and recursively all sub-scopes.
    def calculate(self, targets):
        for target in targets:
            self._calculate_target(target)

        if len(self._errors) or len(self._unset):
            raise ValidationError(self._errors, self._unset)

        return self._arguments


def resolve_configuration(sources: list, targets: list, user_arguments: dict):

    # Make sure all user provided arguments are strings.
    # TODO(cmaloney): Loosen this restriction  / allow arbitrary types as long
    # as they all have a gen specific string form.
    validate_arguments_strings(user_arguments)

    # Merge the sources into a big dictionary of setters + validators, ensuring
    # that all setters are either strings or functions.
    validate = list()
    setters = dict()

    # Merge all the config targets into one big group of setters for providing
    # to the calculator
    # TODO(cmaloney): The setter management / set code is very similar to that in ConfigTarget, they
    # could probably be joined.
    for source in sources:
        for name, setter_list in source.setters.items():
            setters.setdefault(name, list())
            setters[name] += setter_list
        validate += source.validate

    # Validate that targets is a list of Targets
    for target in targets:
        assert isinstance(target, Target), \
            "target should be a Target found a {} with value: {}".format(type(target), target)

    # TODO(cmaloney): Re-enable this after sorting out how to have "optional" config targets which
    # add in extra "acceptable" parameters (SSH Config, AWS Advanced Template config, etc)
    # validate_all_arguments_match_parameters(mandatory_parameters, setters, user_arguments)

    # Add in all user arguments as setters.
    # Happens last so that they are never overwritten with replace_existing=True
    user_config = Source(is_user=True)
    user_config.add_value_dict(user_arguments)

    # Merge all the seters and validate function into one uber list
    setters = copy.deepcopy(user_config.setters)
    validate = copy.deepcopy(user_config.validate)
    for source in sources:
        for name, setter_list in source.setters.items():
            # TODO(cmaloney): Make a setter manager already...
            setters.setdefault(name, list())
            setters[name] += setter_list
        validate += source.validate

    # Use setters to caluclate every required parameter
    arguments = DFSArgumentCalculator(setters, validate).calculate(targets)

    # Validate all new / calculated arguments are strings.
    validate_arguments_strings(arguments)

    log.info("Final arguments:" + json_prettyprint(arguments))

    # TODO(cmaloney) Give each config target the values for all it's parameters that were hit as
    # well as any parameters that led to those parameters.
    return arguments


def validate_configuration(sources: list, targets: list, user_arguments: dict):
    try:
        resolve_configuration(sources, targets, user_arguments)
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
