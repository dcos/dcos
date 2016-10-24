import pytest

import gen
from dcos_installer import cli


def test_default_arg_parser():
    parser = cli.parse_args([])
    assert parser.verbose is False
    assert parser.port == 9000
    assert parser.action is None


def test_set_arg_parser():
    parser = cli.parse_args(['-v', '-p 12345'])
    assert parser.verbose is True
    assert parser.port == 12345
    parser = cli.parse_args(['--web'])
    assert parser.action == 'web'
    parser = cli.parse_args(['--genconf'])
    assert parser.action == 'genconf'
    parser = cli.parse_args(['--preflight'])
    assert parser.action == 'preflight'
    parser = cli.parse_args(['--postflight'])
    assert parser.action == 'postflight'
    parser = cli.parse_args(['--deploy'])
    assert parser.action == 'deploy'
    parser = cli.parse_args(['--validate-config'])
    assert parser.action == 'validate-config'
    parser = cli.parse_args(['--uninstall'])
    assert parser.action == 'uninstall'
    parser = cli.parse_args(['--hash-password', 'foo'])
    assert parser.hash_password == ['foo']
    assert parser.action is None
    parser = cli.parse_args(['--update-config'])
    assert parser.action == 'update-config'

    parser = cli.parse_args(['--set-superuser-password', 'foo'])
    assert parser.set_superuser_password == ['foo']
    assert parser.action is None

    parser = cli.parse_args(['--set-superuser-password'])
    assert parser.set_superuser_password == [None]
    assert parser.action is None

    # Can't do two at once
    with pytest.raises(SystemExit):
        cli.parse_args(['--validate', '--hash-password', 'foo'])


def test_stringify_config():
    stringify = gen.stringify_configuration

    # Basic cases pass right through
    assert dict() == stringify(dict())
    assert {"foo": "bar"} == stringify({"foo": "bar"})
    assert {"a": "b", "c": "d"} == stringify({"a": "b", "c": "d"})

    # booleans are converted to lower case true / false
    assert {"a": "true"} == stringify({"a": True})
    assert {"a": "false"} == stringify({"a": False})
    assert {"a": "b", "c": "false"} == stringify({"a": "b", "c": False})

    # integers are made into strings
    assert {"a": "1"} == stringify({"a": 1})
    assert {"a": "4123"} == stringify({"a": 4123})
    assert {"a": "b", "c": "9999"} == stringify({"a": "b", "c": 9999})

    # Dict and list are converted to JSON
    assert {"a": '["b"]'} == stringify({"a": ['b']})
    assert {"a": '["b\\"a"]'} == stringify({"a": ['b"a']})
    assert {"a": '[1]'} == stringify({"a": [1]})
    assert {"a": '[1, 2, 3, 4]'} == stringify({"a": [1, 2, 3, 4]})
    assert {"a": '[true, false]'} == stringify({"a": [True, False]})
    assert {"a": '{"b": "c"}'} == stringify({"a": {"b": "c"}})
    assert {"a": '{"b": 1}'} == stringify({"a": {"b": 1}})
    assert {"a": '{"b": true}'} == stringify({"a": {"b": True}})
    assert {"a": '{"b": null}'} == stringify({"a": {"b": None}})

    # Random types produce an error.
    with pytest.raises(Exception):
        stringify({"a": set()})

    # All the handled types at once
    assert {
        "a": "b",
        "c": "true",
        "d": "1",
        "e": "[1]",
        "f": '{"g": "h"}'
    } == stringify({"a": "b", "c": True, "d": 1, "e": [1], "f": {"g": "h"}})
