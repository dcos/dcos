"""Tests for verifying key functionality of utilities
"""
import pytest
import requests

from test_util.dcos_api_session import DcosApiSession, DcosUser, get_args_from_env
from test_util.helpers import lazy_property


class MockResponse:
    def __init__(self):
        self.cookies = {'dcos-acs-auth-cookie': 'foo'}

    def raise_for_status(self):
        pass

    def json(self):
        return {'token': 'bar'}


@pytest.fixture
def mock_dcos_client(monkeypatch):
    monkeypatch.setenv('DCOS_DNS_ADDRESS', 'http://mydcos.dcos')
    monkeypatch.setenv('MASTER_HOSTS', '127.0.0.1,0.0.0.0')
    monkeypatch.setenv('PUBLIC_MASTER_HOSTS', '127.0.0.1,0.0.0.0')
    monkeypatch.setenv('SLAVE_HOSTS', '127.0.0.1,123.123.123.123')
    monkeypatch.setenv('PUBLIC_SLAVE_HOSTS', '127.0.0.1,0.0.0.0')
    # covers any request made via the ApiClientSession
    monkeypatch.setattr(requests.Session, 'request', lambda *args, **kwargs: MockResponse())
    monkeypatch.setattr(DcosApiSession, 'wait_for_dcos', lambda self: True)
    args = get_args_from_env()
    args['auth_user'] = None
    return DcosApiSession(**args)


def test_make_user_session(mock_dcos_client):
    # make user session from no auth
    cluster_none = mock_dcos_client
    user_1 = DcosUser({'foo': 'bar'})
    user_2 = DcosUser({'baz': 'qux'})
    cluster_1 = cluster_none.get_user_session(user_1)
    assert cluster_1.session.auth.auth_token == 'bar'
    # Add a cookie to this session to make sure it gets cleared
    cluster_1.session.cookies.update({'dcos-acs-auth-cookie': 'foo'})
    # make user session from user
    cluster_2 = cluster_1.get_user_session(user_2)
    assert cluster_2.session.auth.auth_token == 'bar'
    # check cleared cookie
    assert cluster_2.session.cookies.get('dcos-acs-auth-cookie') is None
    # make no auth session from use session
    cluster_none = cluster_2.get_user_session(None)
    assert cluster_none.session.auth is None
    assert len(cluster_none.session.cookies.items()) == 0


def test_dcos_client_api(mock_dcos_client):
    """ Tests two critical aspects of the DcosApiSession
    1. node keyword arg is supported
    2. all HTTP verbs work
    """
    args = get_args_from_env()
    args['auth_user'] = None
    cluster = DcosApiSession(**args)
    # no assert necessary, just make sure that this function signatures works
    r = cluster.get('', node='123.123.123.123')
    r.raise_for_status()
    cluster.get('')
    cluster.post('')
    cluster.put('')
    cluster.delete('')
    cluster.head('')
    cluster.patch('')
    cluster.options('')


class LazyClass:
    def __init__(self):
        self.property_called = {}

    def _raise_if_called_twice(self, name):
        """ This property can only be called once, as such it can only be a lazy property
        or else multiple calls will raise an error
        """
        if self.property_called.get(name):
            raise AssertionError('This is a lazy property and should only be evaluated exactly once')
        self.property_called[name] = True
        return name

    @property
    def bar(self):
        self._raise_if_called_twice('bar')

    @lazy_property
    def foo(self):
        self._raise_if_called_twice('foo')


def test_lazy_property():
    c = LazyClass()
    c.bar  # will work because its the first call
    with pytest.raises(AssertionError):
        c.bar  # will fail because its a standard property
    c.foo  # will work because its the first call
    c.foo  # will work because function is ignored on second call
