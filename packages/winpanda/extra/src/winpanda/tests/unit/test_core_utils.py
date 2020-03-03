import pytest
import mock

from core import utils
from pathlib import Path
from core.exceptions import RCError, InstallationStorageError
from common.exceptions import InstallationError


def test_rc_load_string_should_fail():
    """Check error validation when path not found."""
    with pytest.raises(AssertionError):
        utils.rc_load_json('')


@mock.patch('core.utils.Path.is_absolute', return_value=True)
def test_rc_load_directory_should_fail(*args):
    """Check error validation when source is directory."""
    with pytest.raises(RCError):
        utils.rc_load_json(Path())


@mock.patch('core.utils.Path.is_absolute', return_value=True)
def test_rc_load_empty_content_should_fail(*args):
    """Check error validation when path is absolute but context has been provided."""
    with pytest.raises(AssertionError):
        utils.rc_load_json(Path(), context='')


@mock.patch('core.utils.Path.open')
@mock.patch('core.utils.Path.is_absolute', return_value=True)
@mock.patch('json.load', return_value={})
def test_rc_load_return_should_provide_json(mock_open, *args):
    """Check does rc_load_json output equal json.load output."""
    mock_open.__enter__.return_value = mock.Mock()
    data = utils.rc_load_json(Path())
    assert data == {}


@mock.patch('core.utils.Path.open')
@mock.patch('core.utils.cfp.ConfigParser')
@mock.patch('core.utils.Path.is_absolute', return_value=True)
def test_rc_load_ini_should_provide_valid_content(mock_open, mock_cfg_parser, *args):
    """Check does rc_load_ini output equal ConfigParser.items."""
    mock_open.__enter__.return_value = mock.Mock()
    mock_cfg_parser().items.return_value = [('itm', [('key', 'val')])]
    data = utils.rc_load_ini(Path())
    assert data == {'itm': {'key': 'val'}}


@mock.patch('core.utils.Path.open')
@mock.patch('core.utils.yaml')
@mock.patch('core.utils.Path.is_absolute', return_value=True)
def test_rc_load_yaml_should_provide_valid_content(mock_open, mock_yaml, *args):
    """Check does rc_load_yaml output equal yaml.safe_load."""
    stub = {'key': 'val'}
    mock_open.__enter__.return_value = mock.Mock()
    mock_yaml.safe_load.return_value = stub
    data = utils.rc_load_yaml(Path())
    assert data == stub


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
