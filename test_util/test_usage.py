"""Tests for verifying key functionality of utilities
"""
import pytest

from test_util.cluster_api import ClusterApi, get_args_from_env
from test_util.helpers import DcosUser


class MockResponse:
    def __init__(self, json, cookies):
        self.json_data = json
        self.cookies = cookies

    def raise_for_status(self):
        pass

    def json(self):
        return self.json_data


@pytest.fixture
def trivial_env(monkeypatch):
    monkeypatch.setenv('DCOS_DNS_ADDRESS', 'http://mydcos.dcos')
    monkeypatch.setenv('MASTER_HOSTS', '127.0.0.1,0.0.0.0')
    monkeypatch.setenv('PUBLIC_MASTER_HOSTS', '127.0.0.1,0.0.0.0')
    monkeypatch.setenv('SLAVE_HOSTS', '127.0.0.1,0.0.0.0')
    monkeypatch.setenv('PUBLIC_SLAVE_HOSTS', '127.0.0.1,0.0.0.0')
    monkeypatch.setenv('DNS_SEARCH', 'false')
    monkeypatch.setenv('DCOS_PROVIDER', 'onprem')


def test_make_user_session(monkeypatch, trivial_env):
    monkeypatch.setattr(ClusterApi, 'post',
                        lambda *args, **kwargs: MockResponse({'token': 'abc'}, {'dcos-acs-auth-cookie': 'foo'}))
    user_1 = DcosUser({'foo': 'bar'})
    user_2 = DcosUser({'baz': 'qux'})
    args = get_args_from_env()
    args['web_auth_default_user'] = user_1
    cluster_none = ClusterApi(**args)
    cluster_1 = cluster_none.get_user_session(user_1)
    cluster_2 = cluster_1.get_user_session(user_2)
    assert cluster_1.default_headers['Authorization'] == 'token=abc'
    assert cluster_2.default_headers['Authorization'] == 'token=abc'
