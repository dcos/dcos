import os

import api_session_fixture
import pytest
from dcos_test_utils import logger

logger.setup(os.getenv('TEST_LOG_LEVEL', 'INFO'))


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
