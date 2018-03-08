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


def pytest_unconfigure(config):
    dcos_api_session = api_session_fixture.make_session_fixture()
    make_diagnostics_report = os.environ.get('DIAGNOSTICS_DIRECTORY') is not None
    if make_diagnostics_report:
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
        dcos_api_session.health.download_diagnostics_reports(bundles)
    else:
        log.info('\nNot downloading diagnostics bundle for this session.')
