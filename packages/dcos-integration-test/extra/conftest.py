import logging
import os

import pytest
import requests
from dcos_test_utils.diagnostics import Diagnostics
from test_helpers import get_expanded_config

log = logging.getLogger(__name__)

pytest_plugins = ['pytest-dcos']


@pytest.fixture(scope='session')
def dcos_api_session(dcos_api_session_factory):
    """ Overrides the dcos_api_session fixture to use
    exhibitor settings currently used in the cluster
    """
    args = dcos_api_session_factory.get_args_from_env()

    exhibitor_admin_password = None
    expanded_config = get_expanded_config()
    if expanded_config['exhibitor_admin_password_enabled'] == 'true':
        exhibitor_admin_password = expanded_config['exhibitor_admin_password']

    api = dcos_api_session_factory(
        exhibitor_admin_password=exhibitor_admin_password,
        **args)
    api.wait_for_dcos()
    return api


def pytest_addoption(parser):
    parser.addoption("--windows-only", action="store_true",
                     help="run only Windows tests")


def pytest_runtest_setup(item):
    if pytest.config.getoption('--windows-only'):
        if item.get_marker('supportedwindows') is None:
            pytest.skip("skipping not supported windows test")
    elif item.get_marker('supportedwindowsonly') is not None:
        pytest.skip("skipping windows only test")


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


def _purge_marathon_nofail(session):
    """
    Try to clean Marathon.
    Do not error if there is a problem.
    """
    try:
        session.marathon.purge()
    except Exception as exc:
        log.exception('Ignoring exception during marathon.purge(): %s', exc)
        if isinstance(exc, requests.exceptions.HTTPError):
            log.error('exc.response.text: %s', exc.response.text)


# Note(JP): Attempt to reset Marathon state before and after every test module
# run in this test suite. This is a brute force approach but we found that the
# problem of side effects as of too careless test isolation and resource
# cleanup became too large.
#
# Note: This is module-scoped so that we can have module- and class-scoped
# fixtures which create Marathon resources.
# The trade-off here is that tests, in particular failing tests, can leak
# resources within a module.
@pytest.fixture(autouse=True, scope='module')
def clean_marathon_state(dcos_api_session):
    """
    Attempt to clean up Marathon state before entering the test module and when
    leaving the test module. Especially attempt to clean up when the test code
    failed. When the cleanup fails do not fail the test but log relevant
    information.
    """
    _purge_marathon_nofail(session=dcos_api_session)
    try:
        yield
    finally:
        _purge_marathon_nofail(session=dcos_api_session)


@pytest.fixture(autouse=False, scope='function')
def clean_marathon_state_function_scoped(dcos_api_session):
    """
    See ``clean_marathon_state`` - this is function scoped as some test modules
    require cleanup after every test.
    """
    _purge_marathon_nofail(session=dcos_api_session)
    try:
        yield
    finally:
        _purge_marathon_nofail(session=dcos_api_session)


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
        last_datapoint = {
            'time': None,
            'value': 0
        }

        health_url = dcos_api_session.default_url.copy(
            query='cache=0',
            path='system/health/v1',
        )

        diagnostics = Diagnostics(
            default_url=health_url,
            masters=dcos_api_session.masters,
            all_slaves=dcos_api_session.all_slaves,
            session=dcos_api_session.copy().session,
        )

        log.info('Create diagnostics report for all nodes')
        diagnostics.start_diagnostics_job()

        log.info('\nWait for diagnostics job to complete')
        diagnostics.wait_for_diagnostics_job(last_datapoint=last_datapoint)

        log.info('\nWait for diagnostics report to become available')
        diagnostics.wait_for_diagnostics_reports()

        log.info('\nDownload zipped diagnostics reports')
        bundles = diagnostics.get_diagnostics_reports()
        diagnostics.download_diagnostics_reports(diagnostics_bundles=bundles)
    else:
        log.info('\nNot downloading diagnostics bundle for this session.')
