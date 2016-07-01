import pytest

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
    assert parser.hash_password == 'foo'
    assert parser.action is None

    # Can't do two at once
    with pytest.raises(SystemExit):
        cli.parse_args(['--validate', '--hash-password', 'foo'])
