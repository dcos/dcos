import pytest

import gen.template
from gen.internals import Scope, Target
from gen.template import For, parse_str, Replacement, Switch, Tokenizer, UnsetParameter


just_text = "foo"
more_complex_text = "foo {"


def get_tokens(str):
    return Tokenizer(str).tokens


def test_lex():
    assert(get_tokens("foo") == [("blob", "foo"), ("eof", None)])
    assert(get_tokens("{") == [('blob', '{'), ('eof', None)])
    assert(get_tokens("{#") == [('blob', '{'), ('blob', '#'), ('eof', None)])
    assert(get_tokens("{  foo  ") == [
           ('blob', '{'), ('blob', '  foo  '), ('eof', None)])
    assert(get_tokens("{ foo {{{{ {{{{{ ") == [('blob', '{'), ('blob', ' foo '), (
        'blob', '{{'), ('blob', ' '), ('blob', '{{'), ('blob', '{'), ('blob', ' '), ('eof', None)])
    assert(get_tokens("{{ test }}") == [
           ('replacement', ('test', None)), ('eof', None)])
    assert(get_tokens("{{ test | foo }}") == [
           ('replacement', ('test', 'foo')), ('eof', None)])
    assert(get_tokens("  {{ test }}") == [
           ('blob', '  '), ('replacement', ('test', None)), ('eof', None)])
    assert(get_tokens("{{ test }}}}") == [
           ('replacement', ('test', None)), ('blob', '}}'), ('eof', None)])
    assert(get_tokens('{% switch foo %}{% case "as\\"df" %}foobar{% endswitch %}}}') == [
           ('switch', 'foo'),
           ('case', 'as"df'),
           ('blob', 'foobar'),
           ('endswitch', None),
           ('blob', '}}'),
           ('eof', None)])
    assert(get_tokens('{% switch foo %}  \n \r {% case "as\\"df" %}foobar{% endswitch %}}}') == [
           ('switch', 'foo'),
           ('blob', '  \n \r '),
           ('case', 'as"df'),
           ('blob', 'foobar'),
           ('endswitch', None),
           ('blob', '}}'),
           ('eof', None)])
    assert(get_tokens("a{% switch foo %}{% case \"test\" %}{{ a | baz }}b{{ a | bar }}{% endswitch %}c{{ c | bar }}{{ a | foo }}") == [  # noqa
            ('blob', 'a'),
            ('switch', 'foo'),
            ('case', 'test'),
            ('replacement', ('a', 'baz')),
            ('blob', 'b'),
            ('replacement', ('a', 'bar')),
            ('endswitch', None),
            ('blob', 'c'),
            ('replacement', ('c', 'bar')),
            ('replacement', ('a', 'foo')),
            ('eof', None)
            ])

    assert(get_tokens("{% for foo in bar %}{{ foo }}{% endfor %}") == [
        ('for', ('foo', 'bar')),
        ('replacement', ('foo', None)),
        ('endfor', None),
        ('eof', None)])

    with pytest.raises(gen.template.SyntaxError):
        get_tokens("{{ test |}}")
    with pytest.raises(gen.template.SyntaxError):
        get_tokens("{{ test|  }}")
    with pytest.raises(gen.template.SyntaxError):
        get_tokens("{{ test |  }}")
    with pytest.raises(gen.template.SyntaxError):
        get_tokens("{{ test  }}")
    with pytest.raises(gen.template.SyntaxError):
        get_tokens("{{test}}")

    with pytest.raises(gen.template.SyntaxError):
        get_tokens("{{ test}}")


def test_parse():
    assert(parse_str("a").ast == ["a"])
    assert(parse_str("{{ a }}").ast == [Replacement(("a", None))])
    assert(parse_str("a {{ a | foo }}{{ b }} c {{ d | bar }}").ast == [
        "a ",
        Replacement(("a", 'foo')),
        Replacement(("b", None)),
        " c ",
        Replacement(("d", 'bar'))
    ])
    assert(parse_str('{% switch foo %}{% case "as\\"df" %}foobar{% endswitch %}}}').ast ==
           [Switch("foo", {'as"df': ["foobar"]}), '}}'])
    assert(parse_str('{{ a }}b{{ c }}{% switch foo %}  \n  {% case "as\\"df" %}foobar{% endswitch %}}}').ast == [
        Replacement(("a", None)),
        "b",
        Replacement(("c", None)),
        Switch("foo", {'as"df': ["foobar"]}),
        "}}"
    ])
    # TODO(cmaloney): Add parse syntax error tests

    assert parse_str("{% for foo in bar %}{{ foo }}{% endfor %}").ast == [For("foo", "bar", [Replacement('foo')])]


def test_target_from_ast():
    assert parse_str("a").target_from_ast() == Target()

    assert parse_str("{{ a }}").target_from_ast() == Target({'a'})
    assert parse_str("{{ a | foo }}").target_from_ast() == Target({'a'})
    assert parse_str("a{{ a }}b{{ c }}").target_from_ast() == Target({'a', 'c'})
    assert parse_str("a{{ a }}b{{ a }}c{{ c | baz }}").target_from_ast() == Target({'a', 'c'})
    assert parse_str("a{{ a }}b{{ a | bar }}c{{ c }}").target_from_ast() == Target({'a', 'c'})
    assert(parse_str("{{ a }}{% switch b %}{% case \"c\" %}{{ d }}{% endswitch %}{{ e }}").target_from_ast() ==
           Target({'a', 'e'}, {'b': Scope('b', {'c': Target({'d'})})}))

    assert (parse_str("{% for foo in bar %}{{ foo }}{{ bar }}{{ baz }}{% endfor %}").target_from_ast() ==
            Target({'bar', 'baz'}))

    # TODO(cmaloney): Disallow reusing a for new variable as a general variable.
    assert (parse_str("{% for foo in bar %}{{ foo }}{{ bar }}{{ baz }}{% endfor %}{{ foo }}").target_from_ast() ==
            Target({'foo', 'bar', 'baz'}))


def test_get_filters():
    assert(parse_str("{{ a }}").get_filters() == set())
    assert(parse_str("{{ a | foo }}").get_filters() == {"foo"})
    assert(parse_str(
        "a{{ a | baz }}b{{ a | bar }}c{{ c | bar }}").get_filters() == {"baz", "bar"})
    assert(parse_str("a{% switch foo %}{% case \"test\" %}{{ a | baz }}b{{ a | bar }}{% endswitch %}c{{ c | bar }}{{ a | foo }}").get_filters() == {"foo", "baz", "bar"})  # noqa
    assert parse_str("{% for foo in bar %}{{ foo | bang }}{% endfor %}").get_filters() == {'bang'}


def test_render():
    assert(parse_str("a").render({}) == "a")
    assert(parse_str("{{ a }}a{{ b }}").render({"a": "1", "b": "2"}) == "1a2")
    assert(parse_str("{{ a | foo }}a{{ b }}").render(
        {"a": "1", "b": "2"},
        {'foo': lambda x: x + 'foo'}
    ) == "1fooa2")
    with pytest.raises(UnsetParameter):
        parse_str("{{ a }}a{{ b }}").render({"a": "1"})
    with pytest.raises(UnsetParameter):
        parse_str("{{ a }}").render({"c": "1"})
    with pytest.raises(UnsetParameter):
        parse_str("{{ a | foo }}").render({"a": "1"})
    assert parse_str("{% for a in b %}{{ a }}{% endfor %}").render({"b": ['a', 'test']}) == "atest"

    assert (parse_str("{% for a in b %}{{ a }}{% endfor %}else{{ a }}").render({"b": ['b', 't', 'c'], "a": "foo"}) ==
            "btcelsefoo")
    with pytest.raises(UnsetParameter):
        parse_str("{% for a in b %}{{ a }}{% endfor %}else{{ a }}").render({"b": ['b', 't', 'c']})
