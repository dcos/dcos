# Various tests that don't fit into the other categories and don't make their own really.

import os

import yaml

from test_helpers import get_expanded_config

__maintainer__ = 'branden'
__contact__ = 'dcos-cluster-ops@mesosphere.io'


# Test that user config is loadable
# TODO(cmaloney): Validate it contains some settings we expact.
def test_load_user_config() -> None:
    with open('/opt/mesosphere/etc/user.config.yaml', 'r') as f:
        user_config = yaml.safe_load(f)

    # Calculated parameters shouldn't be in the user config
    assert 'master_quorum' not in user_config

    # TODO(cmaloney): Test user provided parameters are present. All the
    # platforms have different sets...


def test_expanded_config() -> None:
    expanded_config = get_expanded_config()
    # Caluclated parameters should be present
    assert 'master_quorum' in expanded_config
    # Defined and used parameters should be present
    assert 'marathon_port' in expanded_config
    assert 'mesos_master_port' in expanded_config
    assert 'mesos_agent_port' in expanded_config
    assert 'exhibitor_port' in expanded_config
    assert 'mesos_dns_port' in expanded_config
    assert 'metronome_port' in expanded_config

    # TODO(cmaloney): Test user provided parameters are present. All the
    # platforms have different sets...


def test_profile_symlink() -> None:
    """Assert the DC/OS profile script is symlinked from the correct source."""
    expanded_config = get_expanded_config()
    symlink_target = expanded_config['profile_symlink_target']
    expected_symlink_source = expanded_config['profile_symlink_source']
    assert expected_symlink_source == os.readlink(symlink_target)
