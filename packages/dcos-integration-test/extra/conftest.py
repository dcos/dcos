import logging
import os

import pytest
from test_dcos_diagnostics import (
    _get_bundle_list,
    check_json,
    wait_for_diagnostics_job,
    wait_for_diagnostics_list
)
from test_helpers import expanded_config

log = logging.getLogger(__name__)

pytest_plugins = ['pytest-dcos']


@pytest.fixture(scope='session')
def dcos_api_session(dcos_api_session_factory):
    """ Overrides the dcos_api_session fixture to use
    exhibitor settings currently used in the cluster
    """
    args = dcos_api_session_factory.get_args_from_env()

    exhibitor_admin_password = None
    if expanded_config['exhibitor_admin_password_enabled'] == 'true':
        exhibitor_admin_password = expanded_config['exhibitor_admin_password']

    api = dcos_api_session_factory(
        exhibitor_admin_password=exhibitor_admin_password,
        **args)
    api.wait_for_dcos()
    return api


def pytest_configure(config):
    config.addinivalue_line('markers', 'first: run test before all not marked first')
    config.addinivalue_line('markers', 'last: run test after all not marked last')


def pytest_collection_modifyitems(session, config, items):
    """Reorders test using order mark
    """
    new_items = []
    last_items = []
    for item in items:
        if hasattr(item.obj, 'first'):
            new_items.insert(0, item)
        elif hasattr(item.obj, 'last'):
            last_items.append(item)
        else:
            new_items.append(item)
    items[:] = new_items + last_items


@pytest.fixture(autouse=True)
def clean_marathon_state(dcos_api_session):
    dcos_api_session.marathon.purge()
    yield
    dcos_api_session.marathon.purge()


@pytest.fixture(scope='session')
def noauth_api_session(dcos_api_session):
    return dcos_api_session.get_user_session(None)
