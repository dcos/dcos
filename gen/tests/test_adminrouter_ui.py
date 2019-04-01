from textwrap import dedent

import pytest

import gen
from gen.tests.utils import make_arguments


def test_adminrouter_ui_x_frame_options_default():
    """
    Test that Master Admin Router config file has the correct default
    `X-Frame-Options` value. Defaults are present in `calc.py`.
    """
    config_path = '/etc_master/adminrouter-ui-security.conf'
    arguments = make_arguments(new_arguments={})
    generated = gen.generate(arguments=arguments)
    package = generated.templates['dcos-config.yaml']['package']
    [config] = [item for item in package if item['path'] == config_path]

    expected_configuration = dedent(
        """\
        # Browser security settings for the DC/OS UI
        add_header X-Frame-Options "DENY";
        """
    )
    assert config['content'] == expected_configuration


@pytest.mark.parametrize('value', [
    'DENY',
    'SAMEORIGIN',
    'ALLOW-FROM https://example.com',
    'deny',
    'sameorigin',
    'allow-from https://example.com',
    'allow-from\thttps://example.com',
])
def test_adminrouter_ui_x_frame_options_custom(value):
    """
    Test for all 3 allowed values
    See: https://tools.ietf.org/html/rfc7034#section-2.1
    """
    config_path = '/etc_master/adminrouter-ui-security.conf'
    arguments = make_arguments(new_arguments={
        'adminrouter_x_frame_options': value,
    })
    generated = gen.generate(arguments=arguments)
    package = generated.templates['dcos-config.yaml']['package']
    [config] = [item for item in package if item['path'] == config_path]

    expected_configuration = dedent(
        """\
        # Browser security settings for the DC/OS UI
        add_header X-Frame-Options "{value}";
        """.format(value=value)
    )
    assert config['content'] == expected_configuration


@pytest.mark.parametrize('value', [
    'wrong value',
    'not supported DENY',
    'DENY bad',
    'SAMEORIGIN bad',
    'ALLOW-FROM',
    'allow-from',
])
def test_adminrouter_ui_x_frame_options_validation(value):
    new_arguments = {'adminrouter_x_frame_options': value}
    expected_error_msg = (
        'X-Frame-Options must be set to one of DENY, SAMEORIGIN, ALLOW-FROM'
    )
    result = gen.validate(arguments=make_arguments(new_arguments))
    assert result['status'] == 'errors'

    assert result['errors']['adminrouter_x_frame_options']['message'] == expected_error_msg
