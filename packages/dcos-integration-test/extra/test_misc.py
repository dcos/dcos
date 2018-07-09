# Various tests that don't fit into the other categories and don't make their own really.

import os
import uuid

import pytest
import yaml

from test_helpers import expanded_config

__maintainer__ = 'branden'
__contact__ = 'dcos-cluster-ops@mesosphere.io'


# Test that user config is loadable
# TODO(cmaloney): Validate it contains some settings we expact.
@pytest.mark.supportedwindows
def test_load_user_config():
    with open('/opt/mesosphere/etc/user.config.yaml', 'r') as f:
        user_config = yaml.load(f)

    # Calculated parameters shouldn't be in the user config
    assert 'master_quorum' not in user_config

    # TODO(cmaloney): Test user provided parameters are present. All the
    # platforms have different sets...


@pytest.mark.supportedwindows
def test_expanded_config():
    # Caluclated parameters should be present
    assert 'master_quorum' in expanded_config

    # TODO(cmaloney): Test user provided parameters are present. All the
    # platforms have different sets...


@pytest.mark.supportedwindows
def test_profile_symlink():
    """Assert the DC/OS profile script is symlinked from the correct source."""
    symlink_target = expanded_config['profile_symlink_target']
    expected_symlink_source = expanded_config['profile_symlink_source']
    assert expected_symlink_source == os.readlink(symlink_target)


def test_checks(dcos_api_session):
    base_cmd = [
        '/opt/mesosphere/bin/dcos-shell',
        'dcos-check-runner',
        'check',
    ]
    test_uuid = uuid.uuid4().hex

    # Poststart node checks should pass.
    dcos_api_session.metronome_one_off({
        'id': 'test-checks-node-poststart-' + test_uuid,
        'run': {
            'cpus': .1,
            'mem': 128,
            'disk': 0,
            'cmd': ' '.join(base_cmd + ['node-poststart']),
        },
    })

    # Cluster checks should pass.
    dcos_api_session.metronome_one_off({
        'id': 'test-checks-cluster-' + test_uuid,
        'run': {
            'cpus': .1,
            'mem': 128,
            'disk': 0,
            'cmd': ' '.join(base_cmd + ['cluster']),
        },
    })

    # Check runner should only use the PATH and LD_LIBRARY_PATH from check config.
    dcos_api_session.metronome_one_off({
        'id': 'test-checks-env-' + test_uuid,
        'run': {
            'cpus': .1,
            'mem': 128,
            'disk': 0,
            'cmd': ' '.join([
                'env',
                'PATH=badvalue',
                'LD_LIBRARY_PATH=badvalue',
                '/opt/mesosphere/bin/dcos-check-runner',
                'check',
                'node-poststart',
            ]),
        },
    })
