import copy
import inspect
import logging
from contextlib import contextmanager
from functools import partial, partialmethod
from typing import Callable, List, Tuple, Union

from gen.exceptions import ValidationError
from pkgpanda.build import hash_checkout


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


def function_id(function: Callable):
    return {
        'name': function.__name__,
        'parameters': get_function_parameters(function)
    }


def value_id(value: Union[str, Callable]) -> str:
    if isinstance(value, str):
        return value
    else:
        return function_id(value)


class Setter:

    # NOTE: value may either be a function or a string.
    def __init__(
            self,
            name: str,
            value: Union[str, Callable],
            is_optional: bool,
            conditions: List[Tuple[str, str]],
            is_user: bool):
        self.name = name
        self.is_optional = is_optional
        self.conditions = conditions
        self.is_user = is_user
        self._value_id = hash_checkout(value_id(value))

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

    def make_id(self):
        return {
            'name': self.name,
            'value': self._value_id,
            'is_optional': str(self.is_optional),
            # convert tuple to list since tuple hashing isn't implemented.
            'conditions': [[key, value] for (key, value) in self.conditions],
            'is_user': str(self.is_user)
        }


class Scope:
    def __init__(self, name: str, cases=None):
        self.name = name
        self.cases = cases if cases else dict()

    def add_case(self, value: str, target):
        # Note: Can't make a parameter because target uses Scope for parameters.
        assert isinstance(target, Target)
        self.cases[value] = target

    def __iadd__(self, other):
        # Note: can't use type being defined as parameter type
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
        # Note: can't use type being defined as parameter type
        assert isinstance(other, Scope)
        return self.name == other.name and self.cases == other.cases

    def __repr__(self):
        return "<Scope cases: {}>".format(self.cases.items())


class Target:

    # TODO(cmaloney): Make a better API for working with and managing sub scopes. The current
    # dictionary of dictionaries is really hard to use right.
    def __init__(self, variables=None, sub_scopes=None):
        self.variables = variables if variables else set()
        self.sub_scopes = sub_scopes if sub_scopes else dict()
        self._arguments = None

    def add_variable(self, variable: str):
        self.variables.add(variable)

    def add_scope(self, scope: Scope):
        if scope.name in self.sub_scopes:
            self.sub_scopes[scope.name] += scope
        else:
            self.sub_scopes[scope.name] = scope

    def finalize(self, arguments: dict):
        assert self._arguments is None, "finalize should only be called once. If it was called " \
            "more than once likely some code is re-using a target rather than creating a new " \
            "instance for every resolve_configuration() call"

        # TODO(cmaloney): Walk the tree of things that every argument is
        # dependent upon to get the "full" set of arguments.
        self._arguments = arguments

    @property
    def arguments(self):
        assert self._arguments is not None, "Must only be called after finalize()"
        return self._arguments

    def yield_validates(self):
        # Recursively walk the target / sub scope tree and yield a
        # validate function for each and every switch.
        for name, scope in self.sub_scopes.items():
            # Note: It's important scope.cases.keys() is evaluated now, not later
            # (is evaluated before the validate is called)
            yield name, partial(validate_one_of, valid_values=scope.cases.keys())
            for sub_target in scope.cases.values():
                yield from sub_target.yield_validates()

    def __iadd__(self, other):
        # Note: can't use type being defined as parameter type
        assert isinstance(other, Target), "Internal consistency error, expected Target but got {}".format(type(other))
        self.variables |= other.variables

        # Add all scopes from the other to this, merging all common sub scopes.
        for name, scope in other.sub_scopes.items():
            if name in self.sub_scopes:
                self.sub_scopes[name] += scope
            else:
                self.sub_scopes[name] = scope

        return self

    def __repr__(self):
        return "<Target variables: {}, sub_scopes: {}>".format(self.variables, self.sub_scopes.items())

    def __eq__(self, other):
        # Note: can't use type being defined as parameter type
        assert isinstance(other, Target)
        return self.variables == other.variables and self.sub_scopes == other.sub_scopes


class Source:
    def __init__(self, entry=None, is_user=False):
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

    def make_id(self):
        # {key: [hash_checkout(setter.make_id() for setter in setters)]
        #                 for key, setters in self.setters.items()}
        setter_ids = list()
        for setter_list in self.setters.values():
            for setter in setter_list:
                setter_ids.append(hash_checkout(setter.make_id()))
        return {
            'setters': setter_ids,
            'validate': [hash_checkout(function_id(fn)) for fn in self.validate],
            'is_user': self.is_user
        }


# NOTE: This exception should never escape the Resolver
class CalculatorError(Exception):

    def __init__(self, message: str, chain: list = None):
        if chain is None:
            chain = list()
        self.message = message
        self.chain = chain
        super().__init__(message)


class SkipError(Exception):
    """Raised when this key should silently produce no errors."""
    pass


class Resolvable:
    """ Keeps track of the state of the resolution of a variable with a given name

    - Manages the states (unresolved vs. error / success)
    - Keeps track of what ended up setting the value
    - Keeps track of what caused the resolvable to enter existence (it's cause)
    """

    UNRESOLVED = 'unresolved'
    ERROR = 'error'
    RESOLVED = 'resolved'

    def __init__(self, name):
        self._state = Resolvable.UNRESOLVED
        self.name = name
        self.error = None
        self.setter = None
        self._value = None

    @property
    def is_finalized(self):
        return self._state != Resolvable.UNRESOLVED

    @property
    def is_error(self):
        return self._state == Resolvable.ERROR

    @property
    def is_resolved(self):
        return self._state == Resolvable.RESOLVED

    def finalize_error(self, error):
        assert self._state == Resolvable.UNRESOLVED
        self._state = Resolvable.ERROR
        self.error = error

    def finalize_value(self, value: str, setter: Setter):
        assert self._state == Resolvable.UNRESOLVED
        self._state = Resolvable.RESOLVED
        self._value = value
        self.setter = setter

    @property
    def value(self):
        assert self.is_resolved, "is_resolved() must return true for this function to " \
            "be called. State: {}, is_resolved: {}".format(self._state, self.is_resolved)

        return self._value

    def __str__(self):
        return "<Resolvable name: {}, state: {}>".format(self.name, self._state)


class ArgumentDict(dict):
    """Manages a set of arguments and their values.

    Makes it easy to keep track of a set of resolvables, automatically creating
    a new one when an argument never before asked for is first accessed.
    """

    def __init__(self):
        self._finalized = False

    def __missing__(self, key):
        assert not self._finalized, "No missing keys should be accessed"

        value = self[key] = Resolvable(key)
        return value

    def finalize(self):
        assert not self._finalized
        self._finalized = True


class Validator:
    """Holds a collection of validate functions, and can be asked to call them"""

    def __init__(self, validate_functions, targets):
        # Note: targets must be passed in and inspected here, since the validate_functions that a
        # target yields can't be inspected for the parameter name. To get around this yield_validates
        # returns a two-tuple of the name and a callable.

        # Re-arrange the validation functions so we can more easily access them by
        # argument name.
        self._validate_by_arg = dict()
        self._multi_arg_validate = dict()

        for function in validate_functions:
            parameters = get_function_parameters(function)
            # Could build up the single and multi parameter validation function maps in the same
            # thing but the timing / handling of when and how we run single vs. multi-parameter
            # validation functions is fairly different, the extra bit here simplifies the later code.
            if len(parameters) == 1:
                self._validate_by_arg.setdefault(parameters.pop(), list()).append(function)
            else:
                self._multi_arg_validate.setdefault(frozenset(parameters), list()).append(function)

        for target in targets:
            for parameter, function in target.yield_validates():
                self._validate_by_arg.setdefault(parameter, list()).append(function)

    def validate_single(self, name: str, value: str):
        """Calls all validate functions which validate the given parameter name

        The validate functions will raise an AssertionError which should be caught by the caller
        when validation fails.
        """
        validate_fns = self._validate_by_arg.get(name)
        if validate_fns is not None:
            for validate_fn in validate_fns:
                validate_fn(value)

    # TODO(cmaloney): The distance between the validate_single and multi_arg_validate interface,
    # while necessary for efficient functioning currently, is showing that there is tension between
    # how / when each is run. Moving the multi-argument validation to as soon as possible after an
    # argument set is finalized rather than one big pass at the end would likely make it much
    # cleaner.
    def yield_multi_argument_validate_errors(self, arguments: ArgumentDict):
        for parameter_set, validate_fns in self._multi_arg_validate.items():
            # Build up argument map for validate function. If any arguments are
            # unset then skip this validate function.
            kwargs = dict()
            skip = False
            for parameter in parameter_set:
                # Exit early if the parameter was never calculated / asked for (We don't
                # validate things that are never used or given)
                if parameter not in arguments:
                    skip = True
                    break

                # Exit if the parameter resolved to an error
                resolvable = arguments[parameter]
                if resolvable.is_error:
                    skip = True
                    break

                kwargs[parameter] = arguments[parameter].value

            if skip:
                continue

            # Call the validation function, catching AssertionErrors and turning them into errors in
            # the error dictionary.
            try:
                for validate_fn in validate_fns:
                    validate_fn(**kwargs)
            except AssertionError as ex:
                yield (parameter_set, ex.args[0])


# Depth first search argument calculator. Detects cycles, as well as unmet
# dependencies.
# TODO(cmaloney): Separate chain / path building when unwinding from the root
#                 error messages.
class Resolver:
    def __init__(self, setters, validate_fns, targets):
        self._resolved = False
        self._setters = setters
        self._targets = targets

        self._errors = dict()
        self._unset = set()

        # The current stack of resolvables which are in the process of being resolved.
        self._eval_stack = list()

        # Set of Resolvables() which are resolved, being resolved.
        self._arguments = ArgumentDict()

        self._contexts = list()

        self._validator = Validator(validate_fns, targets)

    def _calculate(self, resolvable):
        # Filter out any setters which have predicates / conditions which are
        # satisfiably false.
        def all_conditions_met(setter):
            for condition_name, condition_value in setter.conditions:
                try:
                    if self._resolve_name(condition_name) != condition_value:
                        return False
                except CalculatorError as ex:
                    raise CalculatorError(
                        ex.message,
                        ex.chain + ['trying to test condition {}={}'.format(condition_name, condition_value)]) from ex
            return True

        # Find the right setter to calculate the argument.
        feasible = list(filter(all_conditions_met, self._setters.get(resolvable.name, list())))

        if len(feasible) == 0:
            self._unset.add(resolvable.name)
            raise SkipError("no way to calculate. Must be set in configuration.")

        # Filtier out all optional setters if there is more than one way to set.
        if len(feasible) > 1:
            final_feasible = list(filter(lambda setter: not setter.is_optional, feasible))
            assert final_feasible, "Had multiple optionals and no musts. Template internal error: {!r}".format(feasible)
            feasible = final_feasible

        # TODO(cmaloney): As long as all paths to set the value evaluate to the same value then
        # having more than one way to calculate is fine. This is true of both multiple internal /
        # system setters, and having multiple user setters.
        # Must be calculated but user tried to provide.
        if len(feasible) == 2 and (feasible[0].is_user or feasible[1].is_user):
            raise CalculatorError("{} must be calculated, but was explicitly set in the "
                                  "configuration. Remove it from the configuration.".format(resolvable.name))
        if len(feasible) > 1:
            raise CalculatorError("Internal error: Multiple ways to set {}. setters: {}".format(
                resolvable.name, feasible))

        setter = feasible[0]

        # Get values for the parameters of the setter than call it to calculate the value.
        kwargs = {}
        for parameter in setter.parameters:
            # TODO(cmaloney): Should catch the exceptions, and wrap with the context of what
            # parameter caused the error to happen so we have a path back to the source value that
            # caused the problem.
            # TODO(cmaloney): Should evaluate all parameters, even if an early one errors, and
            # collect all the error messages to let the user know of as many errors as possible as
            # early as possible.
            kwargs[parameter] = self._resolve_name(parameter)

        try:
            value = setter.calc(**kwargs)
            self._validator.validate_single(resolvable.name, value)
        except AssertionError as ex:
            raise CalculatorError(ex.args[0], [ex]) from ex

        return value, setter

    @contextmanager
    def _stack_layer(self, name):
        # If we're in the middle of resolving it already and find it again, that indicates there
        # was a circular dependency / cycle. Raise an error so that all the resolvers depending on
        # it (including itself) get put into an error state / marked appropriately.
        if name in self._eval_stack:
            raise CalculatorError(
                "Internal error: config calculation cycle detected. Name shouldn't repeat in the "
                "eval stack. name: {} eval_stack: {}".format(
                    name, self._eval_stack), [(name, copy.copy(self._eval_stack),)])
        self._eval_stack.append(name)
        yield
        foo = self._eval_stack.pop()
        assert foo == name, "Internal consistency error: Unwinding stack seems to not be the order it was built in..."

    def _ensure_finalized(self, resolvable):
        if resolvable.is_finalized:
            return

        # Calculate the value, noting that we're in the context of calculating it.
        # NOTE: _stack_layer is outside the try/except so if we find a loop, it will report /
        # finalize on the first instance we passed, rather than finalizing once immediately for
        # the second time the resolvable was encountered, and then trying to finalize a second time
        # when the stack unwinds.
        with self._stack_layer(resolvable.name):
            try:
                resolvable.finalize_value(*self._calculate(resolvable))
            except CalculatorError as ex:
                resolvable.finalize_error(ex)
                self._errors[resolvable.name] = ex.args[0]
            except SkipError as ex:
                resolvable.finalize_error(ex)
            except Exception as ex:
                msg = "Unexpected exception: {}".format(ex)
                resolvable.finalize_error(CalculatorError(msg, [ex]))
                self._errors[resolvable.name] = msg
                raise

    def _resolve_name(self, name):
        try:
            resolvable = self._arguments[name]

            # Ensure the resolvable is resolved
            self._ensure_finalized(resolvable)

        except CalculatorError as ex:
            log.debug("Error calculating %s: %s. Chain: %s", name, ex.message, ex.chain)
            raise
        except SkipError as ex:
            log.debug("Skipping error for key %s: %s", name, ex)
            raise
        finally:
            # The resolvable must have either
            assert resolvable.is_finalized, "_ensure_finalized is supposed to always finalize a " \
                "resolvable but didn't: {}".format(resolvable)

        # If the resolvable is in an error state, raise it so that all the resolvables
        # depending on it will be put into an error state.
        if resolvable.is_error:
            # TODO(cmaloney): Should re-raise the original error with it's original context.
            raise SkipError(
                "Value depended upon {} has an error: {}".format(resolvable.name, resolvable.error),
                [(name, copy.copy(self._eval_stack))])

        return resolvable.value

    def _calculate_target(self, target):
        finalized_arguments = dict()

        # TODO(cmaloney): All the arguments depended upon by the arguments resolved here should be
        # included in the target's full set of finalized arguments.
        for name in target.variables:
            self._ensure_finalized(self._arguments[name])

        for name, sub_scope in target.sub_scopes.items():
            self._ensure_finalized(self._arguments[name])
            resolvable = self._arguments[name]

            assert resolvable.is_finalized, " _resolve_name should have resulted in finalization " \
                "of {}".format(resolvable)

            # Tried solving for the condition but couldn't, so we can't check
            # the sub-scope because we don't know which one to check.
            if resolvable.is_error:
                continue

            assert resolvable.is_resolved, "uhhh: {}".format(resolvable)

            # Must be in the cases since we add validation functions for all switches automatically.
            assert resolvable.value in sub_scope.cases

            # Calculate all the items in the sub-scope
            sub_target = sub_scope.cases[resolvable.value]
            self._calculate_target(sub_target)

            # This .update() is safe because Resolver guarantees each argument
            # only ever has one value / resolvable.
            finalized_arguments.update(sub_target.arguments)

        target.finalize(finalized_arguments)

    # Force calculation of all arguments by accessing the arguments in this
    # scope and recursively all sub-scopes.
    def resolve(self):
        assert not self._resolved, "Resolvers should only be resolved once"
        self._resolved = True

        for target in self._targets:
            self._calculate_target(target)

        for parameter_set, error in self._validator.yield_multi_argument_validate_errors(self._arguments):
            self._errors[parameter_set] = error

    @property
    def arguments(self):
        assert self._resolved, "Can't get arguments until they've been resolved"
        return self._arguments

    @property
    def status_dict(self):
        assert self._resolved, "Can't retrieve status dictionary until configuration has been resolved"
        if not self._errors and not self._unset:
            return {'status': 'ok'}

        # Defer multi-key validation errors and noramlize them to be single-key
        # ones. The multi-key is always less important than the single-key
        # messages which is why single-key messages we never overwrite.
        # TODO(cmaloney): Teach the whole stack to be able to handle multi-key
        # validation errors.
        messages = dict()
        to_do = dict()

        for key, msg in self._errors.items():
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
            'unset': self._unset
        }


def resolve_configuration(sources: List[Source], targets: List[Target]):

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

    # TODO(cmaloney): Re-enable this after sorting out how to have "optional" config targets which
    # add in extra "acceptable" parameters (SSH Config, AWS Advanced Template config, etc)
    # validate_all_arguments_match_parameters(mandatory_parameters, setters, user_arguments)

    user_config = Source(is_user=True)

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
    resolver = Resolver(setters, validate, targets)
    resolver.resolve()

    def target_finalized(target):
        return all([arg.is_finalized for arg in target.arguments.values()])
    assert all(map(target_finalized, targets)), "All targets arguments should have been finalized to values"

    # Validate all new / calculated arguments are strings.
    arg_dict = dict()
    for resolvable in resolver.arguments.values():
        if resolvable.is_error:
            continue
        arg_dict[resolvable.name] = resolvable.value
    validate_arguments_strings(arg_dict)

    return resolver
