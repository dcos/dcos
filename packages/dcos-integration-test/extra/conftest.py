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
    try:
        yield api
    finally:
        api.session.close()


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


@pytest.fixture(scope='session', autouse=True)
def _dump_diagnostics(request, dcos_api_session):
    """Download the zipped diagnostics bundle report from each master in the cluster to the home directory. This should
    be run last. The _ prefix makes sure that pytest calls this first out of the autouse session scope fixtures, which
    means that its post-yield code will be executed last.

    * There is no official way to ensure fixtures are called in a certain order
    https://github.com/pytest-dev/pytest/issues/1216
    * However it seems that fixtures at the same scope are called alphabetically
    https://stackoverflow.com/a/28593102/1436300
    """
    yield

    make_diagnostics_report = os.environ.get('DIAGNOSTICS_DIRECTORY') is not None
    if make_diagnostics_report:
        log.info('Create diagnostics report for all nodes')
        check_json(dcos_api_session.health.post('/report/diagnostics/create', json={"nodes": ["all"]}))

        last_datapoint = {
            'time': None,
            'value': 0
        }

        log.info('\nWait for diagnostics job to complete')
        wait_for_diagnostics_job(dcos_api_session, last_datapoint)

        log.info('\nWait for diagnostics report to become available')
        wait_for_diagnostics_list(dcos_api_session)

        log.info('\nDownload zipped diagnostics reports')
        bundles = _get_bundle_list(dcos_api_session)
        for bundle in bundles:
            for master_node in dcos_api_session.masters:
                r = dcos_api_session.health.get(os.path.join('/report/diagnostics/serve', bundle), stream=True,
                                                node=master_node)
                bundle_path = os.path.join(os.path.expanduser('~'), bundle)
                with open(bundle_path, 'wb') as f:
                    for chunk in r.iter_content(1024):
                        f.write(chunk)
    else:
        log.info('\nNot downloading diagnostics bundle for this session.')
