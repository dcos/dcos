# Various tests that don't fit into the other categories and don't make their own really.
import os

from test_helpers import expanded_config

from pkgpanda.util import load_yaml


# Test that user config is loadable
# TODO(cmaloney): Validate it contains some settings we expact.
def test_load_user_config():
    user_config = load_yaml("/opt/mesosphere/etc/user.config.yaml")

    # Calculated parameters shouldn't be in the user config
    assert 'master_quorum' not in user_config

    # TODO(cmaloney): Test user provided parameters are present. All the
    # platforms have different sets...


def test_expanded_config():
    # Caluclated parameters should be present
    assert 'master_quorum' in expanded_config

    # TODO(cmaloney): Test user provided parameters are present. All the
    # platforms have different sets...


def test_profile_symlink():
    """Assert the DC/OS profile script is symlinked from the correct source."""
    symlink_target = expanded_config['profile_symlink_target']
    expected_symlink_source = expanded_config['profile_symlink_source']
    assert expected_symlink_source == os.readlink(symlink_target)
