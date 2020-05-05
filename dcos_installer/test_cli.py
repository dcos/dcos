import pytest

import gen
from dcos_installer import cli


def test_default_arg_parser():
    parser = cli.get_argument_parser().parse_args([])
    assert parser.verbose is False
    assert parser.port == 9000
    assert parser.action == 'genconf'


def test_set_arg_parser():
    argument_parser = cli.get_argument_parser()

    def parse_args(arg_list):
        return argument_parser.parse_args(arg_list)

    parser = parse_args(['-v', '-p 12345'])
    assert parser.verbose is True
    assert parser.port == 12345
    parser = parse_args(['--web'])
    assert parser.action == 'web'
    parser = parse_args(['--genconf'])
    assert parser.action == 'genconf'
    parser = parse_args(['--hash-password', 'foo'])
    assert parser.password == 'foo'
    assert parser.action == 'hash-password'

    parser = parse_args(['--hash-password'])
    assert parser.password is None
    assert parser.action == 'hash-password'

    parser = parse_args(['--generate-node-upgrade-script', 'fake'])
    assert parser.installed_cluster_version == 'fake'
    assert parser.action == 'generate-node-upgrade-script'

    # Can't do two at once
    with pytest.raises(SystemExit):
        parse_args(['--validate', '--hash-password', 'foo'])


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
