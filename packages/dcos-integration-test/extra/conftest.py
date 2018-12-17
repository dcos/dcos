import datetime
import logging
import os

import pytest
import requests
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


def pytest_addoption(parser):
    parser.addoption("--windows-only", action="store_true",
                     help="run only Windows tests")


def _add_xfail_markers(item):
    """
    Mute flaky Integration Tests with custom pytest marker.
    Rationale for doing this is mentioned at DCOS-45308.
    """
    xfailflake_markers = [
        marker for marker in item.iter_markers() if marker.name == 'xfailflake'
    ]
    for xfailflake_marker in xfailflake_markers:
        assert 'reason' in xfailflake_marker.kwargs
        assert 'jira' in xfailflake_marker.kwargs
        assert xfailflake_marker.kwargs['jira'].startswith('DCOS')
        # Show the JIRA in the printed reason.
        xfailflake_marker.kwargs['reason'] = '{jira} - {reason}'.format(
            jira=xfailflake_marker.kwargs['jira'],
            reason=xfailflake_marker.kwargs['reason'],
        )
        date_text = xfailflake_marker.kwargs['since']
        try:
            datetime.datetime.strptime(date_text, '%Y-%m-%d')
        except ValueError:
            message = (
                'Incorrect date format for "since", should be YYYY-MM-DD'
            )
            raise ValueError(message)

        # The marker is not "strict" unless that is explicitly stated.
        # That means that by default, no error is raised if the test passes or
        # fails.
        strict = xfailflake_marker.kwargs.get('strict', False)
        xfailflake_marker.kwargs['strict'] = strict
        xfail_marker = pytest.mark.xfail(
            *xfailflake_marker.args,
            **xfailflake_marker.kwargs,
        )
        item.add_marker(xfail_marker)


def pytest_runtest_setup(item):
    if pytest.config.getoption('--windows-only'):
        if item.get_marker('supportedwindows') is None:
            pytest.skip("skipping not supported windows test")
    elif item.get_marker('supportedwindowsonly') is not None:
        pytest.skip("skipping windows only test")

    _add_xfail_markers(item)


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


# Note(JP): Attempt to reset Marathon state before and after every test run in
# this test suite. This is a brute force approach but we found that the problem
# of side effects as of too careless test isolation and resource cleanup became
# too large. If this test suite ever introduces a session- or module-scoped
# fixture providing a Marathon app then the `autouse=True` approach will need to
# be relaxed.
@pytest.fixture(autouse=True)
def clean_marathon_state(dcos_api_session):
    """
    Attempt to clean up Marathon state before entering the test and when leaving
    the test. Especially attempt to clean up when the test code failed. When the
    cleanup fails do not fail the test but log relevant information.
    """

    def _purge_nofail():
        try:
            dcos_api_session.marathon.purge()
        except Exception as exc:
            log.exception('Ignoring exception during marathon.purge(): %s', exc)
            if isinstance(exc, requests.exceptions.HTTPError):
                log.error('exc.response.text: %s', exc.response.text)

    _purge_nofail()
    try:
        yield
    finally:
        _purge_nofail()


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
