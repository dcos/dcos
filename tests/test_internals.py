import pytest

import gen.internals
from gen.exceptions import ValidationError
from gen.internals import Scope, Source, Target


def sample_fn_small():
    pass


def sample_fn_normal(foo):
    pass


def sample_fn_big(foo, bar, baz, ping=None, pong="magic"):
    pass


def test_get_function_parameters():
    get_function_parameters = gen.internals.get_function_parameters

    assert get_function_parameters(sample_fn_small) == set()
    assert get_function_parameters(sample_fn_normal) == {'foo'}
    assert get_function_parameters(sample_fn_big) == {'foo', 'bar', 'baz', 'ping', 'pong'}
    assert get_function_parameters(lambda x: x) == {'x'}
    assert get_function_parameters(lambda x, y, a, b: sample_fn_normal(x)) == {'x', 'y', 'a', 'b'}


def test_validate_arguments_strings():
    validate_arguments_strings = gen.internals.validate_arguments_strings

    validate_arguments_strings(dict())
    validate_arguments_strings({'a': 'b'})
    validate_arguments_strings({'a': 'b', 'c': 'd', 'e': 'f'})

    # TODO(cmaloney): Validate the error message contains all error keys.
    with pytest.raises(ValidationError):
        validate_arguments_strings({'a': {'b': 'c'}})

    with pytest.raises(ValidationError):
        validate_arguments_strings({'a': 1})

    with pytest.raises(ValidationError):
        validate_arguments_strings({1: 'a'})

    with pytest.raises(ValidationError):
        validate_arguments_strings({'a': 'b', 'c': 1})

    with pytest.raises(ValidationError):
        validate_arguments_strings({'a': None})


def validate_a(a):
    assert a == 'a_str'


test_source = Source({
    'validate': [validate_a],
    'default': {
        'a': 'a_str',
        'd': 'd_1',
    },
    'must': {
        'b': 'b_str'
    },
    'conditional': {
        'd': {
            'd_1': {
                'must': {
                    'd_1_b': 'd_1_b_str'
                }
            },
            'd_2': {
                'must': {
                    'd_2_b': 'd_2_b_str'
                }
            }
        }
    }
})


def get_test_target():
    return Target(
        {'a', 'b', 'c'},
        {'d': Scope(
            'd', {
                'd_1': Target({'d_1_a', 'd_1_b'}),
                'd_2': Target({'d_2_a', 'd_2_b'})
            })})


def test_resolve_simple():

    test_user_source = Source(is_user=True)
    test_user_source.add_must('c', 'c_str')
    test_user_source.add_must('d_1_a', 'd_1_a_str')

    resolver = gen.internals.resolve_configuration([test_source, test_user_source], [get_test_target()])
    print(resolver)
    assert resolver.status_dict == {'status': 'ok'}

    # Make sure having a unset variable results in a non-ok status
    test_partial_source = Source(is_user=True)
    test_partial_source.add_must('d_1_a', 'd_1_a_str')
    resolver = gen.internals.resolve_configuration([test_source, test_partial_source], [get_test_target()])
    print(resolver)
    assert resolver.status_dict == {'status': 'errors', 'errors': {}, 'unset': {'c'}}


def test_resolve_late():
    test_late_source = Source()
    test_late_source.add_must('c', gen.internals.Late('c_str'))
    test_late_source.add_must('d_1_a', 'd_1_a_str')
    resolver = gen.internals.resolve_configuration([test_source, test_late_source], [get_test_target()])

    assert resolver.status_dict == {'status': 'ok'}
    assert resolver.late == {'c'}

    # TODO(cmaloney): Test resolved from late variables
