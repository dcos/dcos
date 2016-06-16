import pytest

import pkgpanda.util
from pkgpanda import UserManagement
from pkgpanda.exceptions import ValidationError


def test_variant_variations():
    assert pkgpanda.util.variant_str(None) == ''
    assert pkgpanda.util.variant_str('test') == 'test'

    assert pkgpanda.util.variant_name(None) == '<default>'
    assert pkgpanda.util.variant_name('test') == 'test'

    assert pkgpanda.util.variant_prefix(None) == ''
    assert pkgpanda.util.variant_prefix('test') == 'test.'


def test_validate_username():

    def good(name):
        UserManagement.validate_username(name)

    def bad(name):
        with pytest.raises(ValidationError):
            UserManagement.validate_username(name)

    good('dcos_mesos')
    good('dcos_a')
    good('dcos__')
    good('dcos_a_b_c')
    good('dcos_3dt')
    good('dcos_a1')
    good('dcos_1')

    bad('dcos')
    bad('d')
    bad('d_a')
    bad('foobar_asdf')
    bad('dcos_***')
    bad('dc/os_foobar')
    bad('dcos_foo:bar')
    bad('3dcos_foobar')
    bad('dcos3_foobar')
