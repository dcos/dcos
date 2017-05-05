import os

import pytest

from launch.config import get_validated_config, expand_path
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


def test_expand_path(mock_home, mock_relative_path):
    assert expand_path('foo/bar', mock_relative_path) == os.path.join(mock_relative_path, 'foo/bar')
    assert expand_path('~/baz', mock_relative_path) == os.path.join(mock_home, 'baz')


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
        assert 'platform' in exinfo.value.msg


class TestAwsOnprem:
    def test_basic(self, aws_onprem_config_path):
        get_validated_config(aws_onprem_config_path)

    def test_with_key_helper(self, aws_onprem_with_helper_config_path):
        get_validated_config(aws_onprem_with_helper_config_path)

    def test_error_with_nested_config(self, tmpdir):
        with pytest.raises(LauncherError) as exinfo:
            get_validated_config(
                get_temp_config_path(
                    tmpdir, 'aws-onprem-with-helper.yaml',
                    update={'dcos_config': {
                        'ip_detect_content': 'foo',
                        'ip_detect_filename': 'bar'}}))
        assert exinfo.value.error == 'ValidationError'
        assert 'ip_detect' in exinfo.value.msg

    def test_error_is_skipped_in_nested_config(self, tmpdir):
        get_validated_config(
            get_temp_config_path(
                tmpdir, 'aws-onprem-with-helper.yaml',
                update={'dcos_config': {'provider': 'aws'}}))
