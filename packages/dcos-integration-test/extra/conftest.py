import os

import api_session_fixture
import pytest
from requests import Response
from responses import Ok
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


def pytest_assertrepr_compare(op, left, right):
    """Format assertion error message for comparing HTTP responses.
    """
    if isinstance(left, Response) and isinstance(right, Ok) and op == "==":
        if left.request is not None:
            msg = 'Response code from {} was {} {} instead of {}'.format(
                    left.request.url, left.status_code, left.reason,right.expected_code)
        else:
            msg = 'Response code was {} {} instead of {}'.format(
                    left.status_code, left.reason,right.expected_code)
        return ([msg, 'actual body:'] + left.text.splitlines() +
            ['expected body:'] + right.expected_body.splitlines())
