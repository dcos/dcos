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


def test_resolve_simple():

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

    test_target = Target(
        {'a', 'b', 'c'},
        {'d': Scope(
            'd', {
                'd_1': Target({'d_1_a', 'd_1_b'}),
                'd_2': Target({'d_2_a', 'd_2_b'})
            })})

    resolver = gen.internals.resolve_configuration([test_source], [test_target], {'c': 'c_str', 'd_1_a': 'd_1_a_str'})
    print(resolver)
    assert resolver.status_dict == {'status': 'ok'}
