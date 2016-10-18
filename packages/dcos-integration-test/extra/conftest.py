import json
import logging
import os

import pytest

from test_util.cluster_api import ClusterApi
from test_util.helpers import DcosUser
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


@pytest.yield_fixture
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
def user():
    # token valid until 2036 for user albert@bekstil.net
    # {
    #   "email": "albert@bekstil.net",
    #   "email_verified": true,
    #   "iss": "https://dcos.auth0.com/",
    #   "sub": "google-oauth2|109964499011108905050",
    #   "aud": "3yF5TOSzdlI45Q1xspxzeoGBe9fNxm9m",
    #   "exp": 2090884974,
    #   "iat": 1460164974
    # }
    auth_json = {'token': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImtpZCI6Ik9UQkVOakZFTWtWQ09VRTRPRVpGTlRNMFJrWXlRa015Tnprd1JrSkVRemRCTWpBM1FqYzVOZyJ9.eyJlbWFpbCI6ImFsYmVydEBiZWtzdGlsLm5ldCIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJpc3MiOiJodHRwczovL2Rjb3MuYXV0aDAuY29tLyIsInN1YiI6Imdvb2dsZS1vYXV0aDJ8MTA5OTY0NDk5MDExMTA4OTA1MDUwIiwiYXVkIjoiM3lGNVRPU3pkbEk0NVExeHNweHplb0dCZTlmTnhtOW0iLCJleHAiOjIwOTA4ODQ5NzQsImlhdCI6MTQ2MDE2NDk3NH0.OxcoJJp06L1z2_41_p65FriEGkPzwFB_0pA9ULCvwvzJ8pJXw9hLbmsx-23aY2f-ydwJ7LSibL9i5NbQSR2riJWTcW4N7tLLCCMeFXKEK4hErN2hyxz71Fl765EjQSO5KD1A-HsOPr3ZZPoGTBjE0-EFtmXkSlHb1T2zd0Z8T5Z2-q96WkFoT6PiEdbrDA-e47LKtRmqsddnPZnp0xmMQdTr2MjpVgvqG7TlRvxDcYc-62rkwQXDNSWsW61FcKfQ-TRIZSf2GS9F9esDF4b5tRtrXcBNaorYa9ql0XAWH5W_ct4ylRNl3vwkYKWa4cmPvOqT5Wlj9Tf0af4lNO40PQ'}  # noqa
    if 'DCOS_AUTH_JSON_PATH' in os.environ:
        with open(os.environ['DCOS_AUTH_JSON_PATH'], 'r') as auth_json_fh:
            auth_json = json.load(auth_json_fh)
    return DcosUser(auth_json)


@pytest.fixture(scope='session')
def cluster(user):
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

    cluster_api = ClusterApi(
        dcos_uri=os.environ['DCOS_DNS_ADDRESS'],
        masters=os.environ['MASTER_HOSTS'].split(','),
        public_masters=os.environ['PUBLIC_MASTER_HOSTS'].split(','),
        slaves=os.environ['SLAVE_HOSTS'].split(','),
        public_slaves=os.environ['PUBLIC_SLAVE_HOSTS'].split(','),
        dns_search_set=os.environ['DNS_SEARCH'] == 'true',
        provider=os.environ['DCOS_PROVIDER'],
        auth_enabled=os.getenv('DCOS_AUTH_ENABLED', 'true') == 'true',
        default_os_user=os.getenv('DCOS_DEFAULT_OS_USER', 'root'),
        web_auth_default_user=user,
        ca_cert_path=os.getenv('DCOS_CA_CERT_PATH', None))
    cluster_api.wait_for_dcos()
    return cluster_api
