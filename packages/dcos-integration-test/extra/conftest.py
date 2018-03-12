import logging
import os

import api_session_fixture
import pytest
from dcos_test_utils import logger

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


@pytest.fixture(autouse=True)
def clean_marathon_state(dcos_api_session):
    dcos_api_session.marathon.purge()
    yield
    dcos_api_session.marathon.purge()


@pytest.fixture(scope='session')
def dcos_api_session():
    return api_session_fixture.make_session_fixture()


@pytest.fixture(scope='session')
def noauth_api_session(dcos_api_session):
    return dcos_api_session.get_user_session(None)


def pytest_addoption(parser):
    home_dir = os.path.join(os.path.expanduser('~'))
    parser.addoption(
        "--diagnostics",
        nargs='?',
        const=home_dir,
        default=None,
        help="Download a diagnostics bundle .zip file from the cluster at the end of the test run." +
             "Value is directory to put the file in. If no value is set, then it defaults to home directory.")


def make_diagnostics_report(dcos_api_session, write_directory):
    log.info('Create diagnostics report for all nodes')
    dcos_api_session.health.start_diagnostics_job()

    last_datapoint = {
        'time': None,
        'value': 0
    }

    log.info('\nWait for diagnostics job to complete')
    dcos_api_session.health.wait_for_diagnostics_job(last_datapoint)

    log.info('\nWait for diagnostics report to become available')
    dcos_api_session.health.wait_for_diagnostics_reports()

    log.info('\nDownload zipped diagnostics reports')
    bundles = dcos_api_session.health.get_diagnostics_reports()
    dcos_api_session.health.download_diagnostics_reports(bundles, download_directory=write_directory)


def _isdir(maybe_dir):
    """os.path.isdir except it won't raise an Exception on non str, int, byte input"""
    try:
        valid_dir = os.path.isdir(maybe_dir)
    except TypeError as e:
        valid_dir = False
    return valid_dir

dcos_api_session
def pytest_unconfigure(config):
    dcos_api_session = api_session_fixture.make_session_fixture()

    diagnostics_dir = config.getoption('--diagnostics')

    if diagnostics_dir is None:
        log.info('\nNot downloading diagnostics bundle for this session.')
    else:
        user_home = os.path.join(os.path.expanduser('~'))
        warning = '{} is not a directory. Writing diagnostics report to home directory {} instead.'.format(
            diagnostics_dir, user_home)
        if not _isdir(diagnostics_dir):
            log.warn(warning)
            diagnostics_dir = user_home

        make_diagnostics_report(dcos_api_session, diagnostics_dir)
