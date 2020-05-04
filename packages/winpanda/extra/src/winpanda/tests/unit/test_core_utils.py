import pytest
import mock
import yaml

from core import utils
from pathlib import Path
from core.exceptions import RCError, RCInvalidError, RCNotFoundError
from common.exceptions import InstallationError
import jinja2 as jj2


def mock_load_template(func):
    def wrapper(*args, **kwargs):
        with mock.patch('core.utils.Path.open') as mock_open:
            with mock.patch('core.utils.Path.is_absolute', return_value=True):
                mock_open.__enter__.return_value = mock.Mock()
                return func(*args, **kwargs)
    return wrapper


@mock.patch('core.utils.Path.is_absolute', return_value=True)
@mock.patch('core.utils.jj2.Environment.get_template', side_effect=FileNotFoundError)
def test_rc_load_unavailable_template_should_fail(*args):
    """Check template not found issue error handling."""
    with pytest.raises(RCNotFoundError):
        utils.rc_load_json(Path(), render=True)


@mock.patch('core.utils.Path.is_absolute', return_value=True)
def test_rc_load_directory_should_fail(*args):
    """Check error validation when source is directory."""
    with pytest.raises(RCError):
        utils.rc_load_json(Path())


@mock.patch('core.utils.Path.is_absolute', return_value=True)
@mock.patch('core.utils.jj2.Environment.get_template', side_effect=jj2.TemplateError)
def test_rc_load_template_issue_should_fail(*args):
    """Check template errors handling."""
    with pytest.raises(RCInvalidError):
        utils.rc_load_json(Path(), render=True)


@mock.patch('core.utils.Path.is_absolute', return_value=True)
@mock.patch('core.utils.jj2.Environment.get_template', side_effect=mock.Mock())
def test_rc_load_json_template_should_return_dict(mock_template, *args):
    """Check empty json transformation to dict."""
    mock_template().render.return_value = '{}'
    json = utils.rc_load_json(Path(), render=True)
    assert json == {}


@mock_load_template
@mock.patch('json.load', return_value={})
def test_rc_load_json_should_return_dict(*args):
    """Check does rc_load_json output equal json.load output."""
    data = utils.rc_load_json(Path())
    assert data == {}


@mock.patch('core.utils.Path.is_absolute', return_value=True)
@mock.patch('core.utils.jj2.Environment.get_template', side_effect=mock.Mock())
def test_rc_load_ini_template_should_return_dict(mock_template, *args):
    """Check ini transformation to dict."""
    mock_template().render.return_value = '[DEFAULT] \n key: val'
    ini = utils.rc_load_ini(Path(), render=True)
    assert ini == {'DEFAULT': {'key': 'val'}}


@mock_load_template
@mock.patch('core.utils.cfp.ConfigParser')
def test_rc_load_ini_should_provide_valid_content(mock_cfg_parser, *args):
    """Check does rc_load_ini output equal ConfigParser.items."""
    mock_cfg_parser().items.return_value = [('itm', [('key', 'val')])]
    data = utils.rc_load_ini(Path())
    assert data == {'itm': {'key': 'val'}}


@mock.patch('core.utils.Path.is_absolute', return_value=True)
@mock.patch('core.utils.jj2.Environment.get_template', side_effect=mock.Mock())
def test_rc_load_yaml_template_should_return_dict(mock_template, *args):
    """Check yaml transformation to dict."""
    mock_template().render.return_value = 'DEFAULT: \n     key: val'
    ini = utils.rc_load_yaml(Path(), render=True)
    assert ini == {'DEFAULT': {'key': 'val'}}


@mock_load_template
@mock.patch('core.utils.yaml')
def test_rc_load_yaml_should_provide_valid_content(mock_yaml, *args):
    """Check does rc_load_yaml output equal yaml.safe_load."""
    stub = {'key': 'val'}
    mock_yaml.safe_load.return_value = stub
    data = utils.rc_load_yaml(Path())
    assert data == stub


@mock_load_template
@mock.patch('core.utils.yaml.safe_load', side_effect=yaml.YAMLError)
def test_rc_load_yaml_error_should_fail(*args):
    """Check does rc_load_yaml handle YAMLError."""
    with pytest.raises(RCInvalidError):
        utils.rc_load_yaml(Path())


def test_pkg_sort_by_deps_not_dict_should_fail():
    pass

    # TODO check not implemented
    with pytest.raises(TypeError):
        utils.pkg_sort_by_deps(None)

    # TODO empty dict should return empty list
    with pytest.raises(InstallationError):
        utils.pkg_sort_by_deps({})


def test_pkg_sort_order_should_be_correct():
    sorted = utils.pkg_sort_by_deps(packages={
        'vcredist': 'a',
        'nssm': 'b',
        'bootstrap': 'c'})

    assert sorted == ['a', 'b', 'c']
