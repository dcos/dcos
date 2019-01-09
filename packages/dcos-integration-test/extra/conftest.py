import datetime
import os

import api_session_fixture
import pytest
from dcos_test_utils import logger
from dcos_test_utils.diagnostics import Diagnostics

logger.setup(os.getenv('TEST_LOG_LEVEL', 'INFO'))


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
