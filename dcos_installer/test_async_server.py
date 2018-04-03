import asyncio
import os

import aiohttp
import pytest
import webtest_aiohttp

import dcos_installer
import dcos_installer.backend
import dcos_installer.config_util
import gen.calc
from dcos_installer.async_server import build_app
from dcos_installer.config import Config, make_default_config_if_needed
from pkgpanda.util import is_windows, write_string


@pytest.fixture(autouse=True)
def mock_installer_latest_complete_artifact(monkeypatch):
    monkeypatch.setattr(
        dcos_installer.config_util,
        'installer_latest_complete_artifact',
        lambda _: {'bootstrap': os.getenv('BOOTSTRAP_ID', '12345'), 'packages': []},
    )


@pytest.fixture
def client(tmpdir):
    with tmpdir.as_cwd():
        tmpdir.ensure('genconf', dir=True)
        make_default_config_if_needed('genconf/config.yaml')

        # TODO(cmaloney): the app building should probably be per-test-session
        # fixture.
        loop = asyncio.get_event_loop()
        app = build_app(loop)
        client = webtest_aiohttp.TestApp(app)
        client.expect_errors = False

        aiohttp.parsers.StreamWriter.set_tcp_cork = lambda s, v: True
        aiohttp.parsers.StreamWriter.set_tcp_nodelay = lambda s, v: True

        # Yield so that the tmpdir we enter applies to tests this hits.
        # TODO(cmaloney): changing to a tmpdir in the fixutre is weird / probably
        # not the best way to do this, but works for now.
        yield client


def test_redirect_to_root(client):
    route = '/api/v1'
    featured_methods = {
        'GET': [302, 'text/plain', '/'],
        'POST': [405, 'text/plain'],
        'PUT': [405, 'text/plain'],
        'DELETE': [405, 'text/plain'],
        'HEAD': [405, 'text/plain'],
        'TRACE': [405, 'text/plain'],
        'CONNECT': [405, 'text/plain'],
    }
    for method, expected in featured_methods.items():
        res = client.request(route, method=method, expect_errors=True)
        assert res.status_code == expected[0], '{}: {}'.format(
            method,
            expected)
        assert res.content_type == expected[1], '{}: {}'.format(
            method,
            expected)
        if expected[0] == 'GET':
            assert res.location == expected[2], '{}: {}'.format(
                method,
                expected)


def test_get_version(client):
    route = '/api/v1/version'
    res = client.request(route, method='GET')
    assert res.json == {'version': gen.calc.entry['must']['dcos_version']}


def test_configure(client):
    route = '/api/v1/configure'
    featured_methods = {
        'GET': [200, 'application/json'],
        # Should return a 400 if validation has errors,
        # which this POST will return since the ssh_port is not an integer.
        'POST': [400, 'application/json', '{"ssh_port": "asdf"}'],
        'PUT': [405, 'text/plain'],
        'DELETE': [405, 'text/plain'],
        'HEAD': [405, 'text/plain'],
        'TRACE': [405, 'text/plain'],
        'CONNECT': [405, 'text/plain'],
    }

    for method, expected in featured_methods.items():
        if method == 'POST':
            res = client.request(route, method=method, body=bytes(expected[2].encode('utf-8')), expect_errors=True)
        else:
            res = client.request(route, method=method, expect_errors=True)
        assert res.status_code == expected[0], '{}: {}'.format(
            method,
            expected)
        assert res.content_type == expected[1], '{}: {}'.format(
            method,
            expected)
        if expected[0] == 200:
            expected_config = Config('genconf/config.yaml').config
            # Add ui config parameters which are always set.
            # TODO(cmaloney): Make this unnecessary
            expected_config.update({'ssh_key': None, 'ip_detect_script': None})
            assert res.json == expected_config


def test_configure_status(client):
    route = '/api/v1/configure/status'
    featured_methods = {
        # Defaults shouldn't pass validation, expect 400
        'GET': [400, 'application/json'],
        'POST': [405, 'text/plain'],
        'PUT': [405, 'text/plain'],
        'DELETE': [405, 'text/plain'],
        'HEAD': [405, 'text/plain'],
        'TRACE': [405, 'text/plain'],
        'CONNECT': [405, 'text/plain'],
    }

    for method, expected in featured_methods.items():
        res = client.request(route, method=method, expect_errors=True)
        assert res.status_code == expected[0], '{}: {}'.format(method, expected)
        assert res.content_type == expected[1], '{}: {}'.format(method, expected)


def test_success(client, monkeypatch):
    monkeypatch.setattr(dcos_installer.backend, 'success', lambda config: ({}, 200))
    route = '/api/v1/success'
    featured_methods = {
        'GET': [200, 'application/json'],
        'POST': [405, 'text/plain'],
        'PUT': [405, 'text/plain'],
        'DELETE': [405, 'text/plain'],
        'HEAD': [405, 'text/plain'],
        'TRACE': [405, 'text/plain'],
        'CONNECT': [405, 'text/plain'],
    }

    for method, expected in featured_methods.items():
        res = client.request(route, method=method, expect_errors=True)
        assert res.status_code == expected[0], '{}: {}'.format(
            method,
            expected)
        assert res.content_type == expected[1], '{}: {}'.format(
            method,
            expected)


def action_action_name(route):
    featured_methods = {
        'GET': [200, 'application/json'],
        'POST': [200, 'application/json'],
        'PUT': [405, 'text/plain'],
        'DELETE': [405, 'text/plain'],
        'HEAD': [405, 'text/plain'],
        'TRACE': [405, 'text/plain'],
        'CONNECT': [405, 'text/plain'],
    }

    for method, expected in featured_methods.items():
        res = client.request(route, method=method, expect_errors=True)
        assert res.status_code == expected[0], '{}: {}'.format(
            method,
            expected)
        assert res.content_type == expected[1], '{}: {}'.format(
            method,
            expected)


def action_side_effect_return_config(arg):
    return {
        arg: {
            'mock_config': True
        }
    }


def mock_json_state(monkeypatch, new_fn):
    monkeypatch.setattr(dcos_installer.async_server, 'read_json_state', new_fn)


def mock_action_result(monkeypatch, name):
    monkeypatch.setattr(dcos_installer.action_lib, name, lambda x: (i for i in range(10)))


def test_action_preflight(client, monkeypatch):
    route = '/api/v1/action/preflight'
    mock_json_state(monkeypatch, action_side_effect_return_config)
    mock_action_result(monkeypatch, 'run_preflight')

    res = client.request(route, method='GET')
    assert res.json == {'preflight': {'mock_config': True}}

    mock_json_state(monkeypatch, lambda _: {})
    res = client.request(route, method='GET')
    assert res.json == {}


def test_action_postflight(client, monkeypatch):
    route = '/api/v1/action/postflight'
    mock_json_state(monkeypatch, action_side_effect_return_config)
    mock_action_result(monkeypatch, 'run_postflight')

    res = client.request(route, method='GET')
    assert res.json == {'postflight': {'mock_config': True}}

    mock_json_state(monkeypatch, lambda _: {})
    res = client.request(route, method='GET')
    assert res.json == {}


def test_action_deploy(client, monkeypatch):
    route = '/api/v1/action/deploy'
    mock_json_state(monkeypatch, action_side_effect_return_config)
    mock_action_result(monkeypatch, 'install_dcos')

    res = client.request(route, method='GET')
    assert res.json == {'deploy': {'mock_config': True}}

    mock_json_state(monkeypatch, lambda _: {})
    res = client.request(route, method='GET')
    assert res.json == {}


def test_action_current(client):
    route = '/api/v1/action/current'
    featured_methods = {
        'GET': [200, 'application/json'],
        'POST': [405, 'text/plain'],
        'PUT': [405, 'text/plain'],
        'DELETE': [405, 'text/plain'],
        'HEAD': [405, 'text/plain'],
        'TRACE': [405, 'text/plain'],
        'CONNECT': [405, 'text/plain'],
    }
    for method, expected in featured_methods.items():
        res = client.request(route, method=method, expect_errors=True)
        assert res.status_code == expected[0], '{}: {}'.format(
            method,
            expected)
        assert res.content_type == expected[1], '{}: {}'.format(
            method,
            expected)


def test_configure_type(client):
    route = '/api/v1/configure/type'
    featured_methods = {
        'GET': [200, 'application/json'],
        'POST': [405, 'text/plain'],
        'PUT': [405, 'text/plain'],
        'DELETE': [405, 'text/plain'],
        'HEAD': [405, 'text/plain'],
        'TRACE': [405, 'text/plain'],
        'CONNECT': [405, 'text/plain'],
    }

    for method, expected in featured_methods.items():
        res = client.request(route, method=method, expect_errors=True)
        assert res.status_code == expected[0], '{}: {}'.format(
            method,
            expected)
        assert res.content_type == expected[1], '{}: {}'.format(
            method,
            expected)


ssh_config_yaml = '''
ssh_user: centos
master_list:
 - 127.0.0.1
agent_list:
 - 127.0.0.2
public_agent_list: []
'''


@pytest.mark.skipif(is_windows, reason="test fails on Windows reason unknown")
def test_action_deploy_post(client, monkeypatch):
    route = '/api/v1/action/deploy'

    write_string('genconf/config.yaml', ssh_config_yaml)
    monkeypatch.setattr(dcos_installer.action_lib, '_get_bootstrap_tarball', lambda: '123')
    monkeypatch.setattr(dcos_installer.action_lib, '_get_cluster_package_list', lambda: '123')
    monkeypatch.setattr(dcos_installer.action_lib, '_add_copy_packages', lambda _: None)

    # Deploy should be already executed for action 'deploy'
    def mocked_json_state(arg):
        return {
            'hosts': {
                '127.0.0.1': {
                    'host_status': 'success'
                },
                '127.0.0.2': {
                    'host_status': 'success'
                }
            }
        }
    mock_json_state(monkeypatch, mocked_json_state)
    res = client.request(route, method='POST')
    assert res.json == {'status': 'deploy was already executed, skipping'}

    # Test start deploy
    mock_json_state(monkeypatch, lambda arg: False)
    res = client.request(route, method='POST')
    assert res.json == {'status': 'deploy started'}


def test_action_deploy_retry(client, monkeypatch):
    route = '/api/v1/action/deploy'

    write_string('genconf/config.yaml', ssh_config_yaml)
    monkeypatch.setattr(dcos_installer.action_lib, '_get_bootstrap_tarball', lambda: '123')
    monkeypatch.setattr(dcos_installer.action_lib, '_get_cluster_package_list', lambda: '123')
    monkeypatch.setattr(dcos_installer.action_lib, '_add_copy_packages', lambda _: None)
    monkeypatch.setattr(dcos_installer.action_lib, '_read_state_file', lambda state_file: {'total_hosts': 2})

    removed_hosts = list()

    def mocked_remove_host(state_file, host):
        removed_hosts.append(host)

    monkeypatch.setattr(dcos_installer.action_lib, '_remove_host', mocked_remove_host)

    # Test retry
    def mocked_json_state(arg):
        return {
            'hosts': {
                '127.0.0.1:22': {
                    'host_status': 'failed',
                    'tags': {'role': 'master', 'dcos_install_param': 'master'},
                },
                '127.0.0.2:22022': {
                    'host_status': 'success'
                },
                '127.0.0.3:22022': {
                    'host_status': 'failed',
                    'tags': {'role': 'agent', 'dcos_install_param': 'slave'},
                }
            }
        }

    mock_json_state(monkeypatch, mocked_json_state)
    res = client.post(route, params={'retry': 'true'}, content_type='application/x-www-form-urlencoded')
    assert res.json == {'details': ['127.0.0.1:22', '127.0.0.3:22022'], 'status': 'retried'}
    assert len(set(removed_hosts)) == 2, \
        "Should have had two hosts removed exactly once, removed_hosts: {}".format(removed_hosts)
    assert set(removed_hosts) == {'127.0.0.3:22022', '127.0.0.1:22'}


def test_unlink_state_file(monkeypatch):
    monkeypatch.setattr(os.path, 'isfile', lambda x: True)

    def mocked_unlink(path):
        assert path == 'genconf/state/preflight.json'

    monkeypatch.setattr(os, 'unlink', mocked_unlink)
    dcos_installer.async_server.unlink_state_file('preflight')
