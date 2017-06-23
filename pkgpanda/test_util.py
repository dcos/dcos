import pytest

import pkgpanda.util
from pkgpanda import UserManagement
from pkgpanda.exceptions import ValidationError


def test_variant_variations():
    assert pkgpanda.util.variant_str(None) == ''
    assert pkgpanda.util.variant_str('test') == 'test'

    assert pkgpanda.util.variant_object('') is None
    assert pkgpanda.util.variant_object('test') == 'test'

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


def test_validate_group():
    # assuming linux distributions have `root` group.
    UserManagement.validate_group('root')

    with pytest.raises(ValidationError):
        UserManagement.validate_group('group-should-not-exist')


def test_split_by_token():
    split_by_token = pkgpanda.util.split_by_token

    # Token prefix and suffix must not be empty.
    with pytest.raises(ValueError):
        list(split_by_token('', ')', 'foo'))
    with pytest.raises(ValueError):
        list(split_by_token('(', '', 'foo'))
    with pytest.raises(ValueError):
        list(split_by_token('', '', 'foo'))

    # Empty string.
    assert list(split_by_token('{{ ', ' }}', '')) == [('', False)]

    # String with no tokens.
    assert list(split_by_token('{{ ', ' }}', 'no tokens')) == [('no tokens', False)]

    # String with one token.
    assert list(split_by_token('{{ ', ' }}', '{{ token_name }}')) == [('{{ token_name }}', True)]
    assert list(split_by_token('{{ ', ' }}', 'foo {{ token_name }}')) == [('foo ', False), ('{{ token_name }}', True)]
    assert list(split_by_token('{{ ', ' }}', '{{ token_name }} foo')) == [('{{ token_name }}', True), (' foo', False)]

    # String with multiple tokens.
    assert list(split_by_token('{{ ', ' }}', 'foo {{ token_a }} bar {{ token_b }} \n')) == [
        ('foo ', False), ('{{ token_a }}', True), (' bar ', False), ('{{ token_b }}', True), (' \n', False)
    ]

    # Token decoration is stripped when requested.
    assert list(split_by_token('[[', ']]', 'foo [[token_a]] bar[[token_b ]]', strip_token_decoration=True)) == [
        ('foo ', False), ('token_a', True), (' bar', False), ('token_b ', True)
    ]

    # Token prefix and suffix can be the same.
    assert list(split_by_token('||', '||', 'foo ||token_a|| bar ||token_b|| \n')) == [
        ('foo ', False), ('||token_a||', True), (' bar ', False), ('||token_b||', True), (' \n', False)
    ]
    assert list(split_by_token('||', '||', 'foo ||token_a|| bar ||token_b|| \n', strip_token_decoration=True)) == [
        ('foo ', False), ('token_a', True), (' bar ', False), ('token_b', True), (' \n', False)
    ]

    # Missing token suffix.
    with pytest.raises(Exception):
        list(split_by_token('(', ')', '(foo) (bar('))
    # Missing suffix for middle token.
    with pytest.raises(Exception):
        list(split_by_token('[[', ']]', '[[foo]] [[bar [[baz]]'))
    # Missing token prefix.
    with pytest.raises(Exception):
        list(split_by_token('[[', ']]', 'foo]] [[bar]]'))
    # Nested tokens.
    with pytest.raises(Exception):
        list(split_by_token('[[', ']]', '[[foo]] [[bar [[baz]] ]]'))

    # Docstring examples.
    assert list(split_by_token('{', '}', 'some text {token} some more text')) == [
        ('some text ', False), ('{token}', True), (' some more text', False)
    ]
    assert list(split_by_token('{', '}', 'some text {token} some more text', strip_token_decoration=True)) == [
        ('some text ', False), ('token', True), (' some more text', False)
    ]
