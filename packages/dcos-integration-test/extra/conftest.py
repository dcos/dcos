import logging
import os

import pytest

import test_util.cluster_api

LOG_LEVEL = logging.INFO


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

    return test_util.cluster_api.ClusterApi(
        dcos_uri=os.environ['DCOS_DNS_ADDRESS'],
        masters=os.environ['MASTER_HOSTS'].split(','),
        public_masters=os.environ['PUBLIC_MASTER_HOSTS'].split(','),
        slaves=os.environ['SLAVE_HOSTS'].split(','),
        public_slaves=os.environ['PUBLIC_SLAVE_HOSTS'].split(','),
        dns_search_set=os.environ['DNS_SEARCH'],
        provider=os.environ['DCOS_PROVIDER'],
        auth_enabled=os.getenv('DCOS_AUTH_ENABLED', 'true') == 'true',
        username=os.getenv('DCOS_LOGIN_UNAME', None),
        password=os.getenv('DCOS_LOGIN_PW', None))
