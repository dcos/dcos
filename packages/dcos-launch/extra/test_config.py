import os

import pytest
import yaml

from launch.config import gen_format_config, get_validated_config
from launch.util import get_temp_config_path, LauncherError


@pytest.fixture
def mock_home(tmpdir):
    home_cache = os.getenv('HOME', None)
    os.environ['HOME'] = str(tmpdir)
    yield str(tmpdir)
    if home_cache is not None:
        os.environ['HOME'] = home_cache
    else:
        del os.environ['HOME']


@pytest.fixture
def mock_relative_path(tmpdir):
    with tmpdir.as_cwd():
        yield str(tmpdir)


def test_gen_formatting(mock_home, mock_relative_path):
    config = {
        'foobarbaz': True,
        'fizzbuzz': 3}

    abs_config = {'foo_filename': '/abc'}
    foo_filename = '/abc'
    config.update(abs_config)
    config['foo'] = abs_config  # Test single nest

    rel_config = {'bar_filename': 'some_other_dir'}
    config.update(rel_config)
    bar_filename = os.path.join(mock_relative_path, 'some_other_dir')
    config['bar'] = {'bar': rel_config}  # Test double nested

    user_config = {'baz_filename': '~/foo/bar/dir'}
    baz_filename = os.path.join(mock_home, 'foo/bar/dir')
    config.update(user_config)
    config['baz'] = {'baz': {'baz': user_config}}  # Test triple-nested

    assert gen_format_config(config, mock_relative_path) == {
        'foobarbaz': 'true',
        'fizzbuzz': '3',
        'foo_filename': foo_filename,
        'bar_filename': bar_filename,
        'baz_filename': baz_filename,
        'foo': yaml.dump({'foo_filename': foo_filename}),
        'bar': yaml.dump({'bar': {'bar_filename': bar_filename}}),
        'baz': yaml.dump({'baz': {'baz': {'baz_filename': baz_filename}}})}


class TestAwsCloudformation:
    def test_basic(self, aws_cf_config_path):
        get_validated_config(aws_cf_config_path)

    def test_with_key_helper(self, aws_cf_with_helper_config_path):
        get_validated_config(aws_cf_with_helper_config_path)

    def test_with_zen_helper(self, aws_zen_cf_config_path):
        get_validated_config(aws_zen_cf_config_path)

    def test_without_pytest_support(self, aws_cf_no_pytest_config_path):
        get_validated_config(aws_cf_no_pytest_config_path)

    def test_error_with_installer_url(self, tmpdir):
        with pytest.raises(LauncherError) as exinfo:
            get_validated_config(
                get_temp_config_path(
                    tmpdir, 'aws-cf-with-helper.yaml', update={'installer_url': 'foobar'}))
        assert exinfo.value.error == 'ValidationError'
        assert 'installer_url' in exinfo.value.msg
        assert 'Unrecognized/incompatible' in exinfo.value.msg


class TestAzureTemplate:
    def test_basic(self, azure_config_path):
        get_validated_config(azure_config_path)

    def test_with_key_helper(self, azure_with_helper_config_path):
        get_validated_config(azure_with_helper_config_path)

    def test_error_wrong_platform(self, tmpdir):
        with pytest.raises(LauncherError) as exinfo:
            get_validated_config(
                get_temp_config_path(
                    tmpdir, 'azure-with-helper.yaml', update={'platform': 'aws'}))
        assert exinfo.value.error == 'ValidationError'
        assert 'platform must be calculated' in exinfo.value.msg


class TestAwsOnprem:
    def test_basic(self, aws_onprem_config_path):
        get_validated_config(aws_onprem_config_path)

    def test_with_key_helper(self, aws_onprem_with_helper_config_path):
        get_validated_config(aws_onprem_with_helper_config_path)

    def test_error_with_nested_config(self, tmpdir):
        with pytest.raises(LauncherError) as exinfo:
            get_validated_config(
                get_temp_config_path(
                    tmpdir, 'aws-onprem-with-helper.yaml', update={'dcos_config': {'provider': 'aws'}}))
        assert exinfo.value.error == 'ValidationError'
        assert 'onprem_dcos_config_contents' in exinfo.value.msg
