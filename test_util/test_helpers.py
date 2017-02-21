"""Tests for test_util.helpers."""
import pytest

from test_util import helpers


def test_marathon_app_id_to_mesos_dns_subdomain():
    assert helpers.marathon_app_id_to_mesos_dns_subdomain('/app-1') == 'app-1'
    assert helpers.marathon_app_id_to_mesos_dns_subdomain('app-1') == 'app-1'
    assert helpers.marathon_app_id_to_mesos_dns_subdomain('/group-1/app-1') == 'app-1-group-1'


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

    @helpers.lazy_property
    def foo(self):
        self._raise_if_called_twice('foo')


def test_lazy_property():
    c = LazyClass()
    c.bar  # will work because its the first call
    with pytest.raises(AssertionError):
        c.bar  # will fail because its a standard property
    c.foo  # will work because its the first call
    c.foo  # will work because function is ignored on second call
