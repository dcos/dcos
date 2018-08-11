import os

import pytest

import release
from pkgpanda.util import is_windows


@pytest.fixture
def release_config():
    if not os.path.exists('dcos-release.config.yaml'):
        pytest.skip("Skipping because there is no configuration in dcos-release.config.yaml")
    return release.load_config('dcos-release.config.yaml')


@pytest.fixture
def release_config_testing(release_config):
    if 'testing' not in release_config:
        pytest.skip("Skipped because there is no `testing` configuration in dcos-release.config.yaml")
    return release_config['testing']


@pytest.fixture
def release_config_aws(release_config_testing):
    if is_windows:
        pytest.skip("Skipped because AWS is not supported on Windows")
    if 'aws' not in release_config_testing:
        pytest.skip("Skipped because there is no `testing.aws` configuration in dcos-release.config.yaml")
    return release_config_testing['aws']


@pytest.fixture
def release_config_azure(release_config_testing):
    if 'azure' not in release_config_testing:
        pytest.skip("Skipped because there is no `testing.azure` configuration in dcos-release.config.yaml")
    return release_config_testing['azure']
