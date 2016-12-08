import logging

import pytest

from test_util.cluster_fixture import make_cluster_fixture
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
def vip_apps(cluster):
    vip1 = '6.6.6.1:6661'
    test_app1, _ = get_test_app()
    test_app1['portDefinitions'][0]['labels'] = {
        'VIP_0': vip1}
    test_app2, _ = get_test_app()
    test_app2['portDefinitions'][0]['labels'] = {
        'VIP_0': 'foobarbaz:5432'}
    vip2 = 'foobarbaz.marathon.l4lb.thisdcos.directory:5432'
    with cluster.marathon.deploy_and_cleanup(test_app1):
        with cluster.marathon.deploy_and_cleanup(test_app2):
            yield ((test_app1, vip1), (test_app2, vip2))


@pytest.fixture(scope='session')
def cluster():
    return make_cluster_fixture()
