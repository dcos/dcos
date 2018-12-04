import logging
import os

import api_session_fixture
import pytest
from dcos_test_utils import logger
from test_dcos_diagnostics import (
    _get_bundle_list,
    check_json,
    wait_for_diagnostics_job,
    wait_for_diagnostics_list
)
logger.setup(os.getenv('TEST_LOG_LEVEL', 'INFO'))
log = logging.getLogger(__name__)


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


# Note(JP): Attempt to reset Marathon state before and after every
# test run in this test suite. This is a brute force approach but
# we found that the problem of side effects as of too careless
# test isolation and resource cleanup became too large.
@pytest.fixture(autouse=True)
def clean_marathon_state(dcos_api_session):
    dcos_api_session.marathon.purge()
    try:
        yield
    finally:
        # This is in `finally:` so that we attempt to clean up
        # Marathon state especially when the test code failed.
        dcos_api_session.marathon.purge()


@pytest.fixture(scope='session')
def dcos_api_session():
    return api_session_fixture.make_session_fixture()


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
