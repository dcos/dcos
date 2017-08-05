import logging

import pytest

from api_session_fixture import make_session_fixture

logging.basicConfig(format='[%(asctime)s] %(levelname)s: %(message)s', level=logging.INFO)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)


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
    return make_session_fixture()


@pytest.fixture(scope='session')
def noauth_api_session(dcos_api_session):
    return dcos_api_session.get_user_session(None)
