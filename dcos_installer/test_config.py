from dcos_installer import config
from gen.exceptions import ValidationError


def test_normalize_config_validation_exception():
    errors = {
        'key': {'message': 'test'},
    }
    validation_error = ValidationError(errors=errors, unset=set(['one', 'two']))
    normalized = config.normalize_config_validation_exception(validation_error)

    expected = {
        'key': 'test',
        'one': 'Must set one, no way to calculate value.',
        'two': 'Must set two, no way to calculate value.',
    }
    assert expected == normalized
