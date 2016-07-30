# Various tests that don't fit into the other categories and don't make their own really.
import json
import yaml


# Test that user config is loadable
# TODO(cmaloney): Validate it contains some settings we expact.
def test_load_user_config():
    with open("/opt/mesosphere/etc/user.config.yaml", "r") as f:
        user_config = yaml.load(f)

    # Calculated parameters shouldn't be in the user config
    assert 'master_quorum' not in user_config

    # TODO(cmaloney): Test user provided parameters are present. All the
    # platforms have different sets...


def test_load_expanded_config():
    with open("/opt/mesosphere/etc/expanded.config.json", "r") as f:
        expanded_config = json.load(f)

    # Caluclated parameters should be present
    assert 'master_quorum' in expanded_config

    # TODO(cmaloney): Test user provided parameters are present. All the
    # platforms have different sets...
