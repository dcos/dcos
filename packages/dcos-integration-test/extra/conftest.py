import logging

import pytest

from api_session_fixture import make_session_fixture

from test_util.marathon import get_test_app

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


@pytest.fixture
def vip_apps(dcos_api_session):
    vip1 = '6.6.6.1:6661'
    test_app1, _ = get_test_app(vip=vip1)
    name = 'foobarbaz'
    port = 5432
    test_app2, _ = get_test_app(vip='{}:{}'.format(name, port))
    vip2 = '{}.marathon.l4lb.thisdcos.directory:{}'.format(name, port)
    with dcos_api_session.marathon.deploy_and_cleanup(test_app1):
        with dcos_api_session.marathon.deploy_and_cleanup(test_app2):
            yield ((test_app1, vip1), (test_app2, vip2))


@pytest.fixture(scope='session')
def dcos_api_session():
    return make_session_fixture()


@pytest.fixture(scope='session')
def noauth_api_session(dcos_api_session):
    return dcos_api_session.get_user_session(None)
