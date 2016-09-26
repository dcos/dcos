import logging
import os

import pytest

import test_util.cluster_api

LOG_LEVEL = logging.INFO


def pytest_configure(config):
    config.addinivalue_line('markers', 'first: run test before all not marked first')
    config.addinivalue_line('markers', 'last: run test after all not marked last')
    config.addinivalue_line('markers', 'resiliency: Run tests that cause critical failures')


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


def pytest_addoption(parser):
    parser.addoption('--resiliency', action='store_true')


def pytest_runtest_setup(item):
    if item.get_marker('resiliency'):
        if not item.config.getoption('--resiliency'):
            pytest.skip('Test requires --resiliency option')


@pytest.yield_fixture
def vip_apps(cluster):
    vip1 = '6.6.6.1:6661'
    test_app1, _ = cluster.get_test_app()
    test_app1['portDefinitions'][0]['labels'] = {
        'VIP_0': vip1}
    test_app2, _ = cluster.get_test_app()
    test_app2['portDefinitions'][0]['labels'] = {
        'VIP_0': 'foobarbaz:5432'}
    vip2 = 'foobarbaz.marathon.l4lb.thisdcos.directory:5432'
    with cluster.marathon_deploy_and_cleanup(test_app1):
        with cluster.marathon_deploy_and_cleanup(test_app2):
            yield ((test_app1, vip1), (test_app2, vip2))


@pytest.fixture(scope='session')
def cluster():
    assert 'DCOS_DNS_ADDRESS' in os.environ
    assert 'MASTER_HOSTS' in os.environ
    assert 'PUBLIC_MASTER_HOSTS' in os.environ
    assert 'SLAVE_HOSTS' in os.environ
    assert 'PUBLIC_SLAVE_HOSTS' in os.environ
    assert 'DNS_SEARCH' in os.environ
    assert 'DCOS_PROVIDER' in os.environ

    # dns_search must be true or false (prevents misspellings)
    assert os.environ['DNS_SEARCH'] in ['true', 'false']

    assert os.environ['DCOS_PROVIDER'] in ['onprem', 'aws', 'azure']

    logging.basicConfig(format='[%(asctime)s] %(levelname)s: %(message)s', level=LOG_LEVEL)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)

    cluster_api = test_util.cluster_api.ClusterApi(
        dcos_uri=os.environ['DCOS_DNS_ADDRESS'],
        masters=os.environ['MASTER_HOSTS'].split(','),
        public_masters=os.environ['PUBLIC_MASTER_HOSTS'].split(','),
        slaves=os.environ['SLAVE_HOSTS'].split(','),
        public_slaves=os.environ['PUBLIC_SLAVE_HOSTS'].split(','),
        dns_search_set=os.environ['DNS_SEARCH'],
        provider=os.environ['DCOS_PROVIDER'],
        auth_enabled=os.getenv('DCOS_AUTH_ENABLED', 'true') == 'true',
        username=os.getenv('DCOS_LOGIN_UNAME', None),
        password=os.getenv('DCOS_LOGIN_PW', None),
        default_os_user=os.getenv('DCOS_DEFAULT_OS_USER', 'root'))
    cluster_api.wait_for_dcos()
    return cluster_api
