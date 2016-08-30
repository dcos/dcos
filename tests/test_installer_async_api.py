import asyncio

import pytest

import aiohttp
import gen.calc
import webtest_aiohttp
from dcos_installer import action_lib
from dcos_installer.async_server import build_app
from ssh.ssh_runner import Node

version = 1


@pytest.fixture(scope='session')
def client():
    loop = asyncio.get_event_loop()
    app = build_app(loop)
    client = webtest_aiohttp.TestApp(app)
    client.expect_errors = False

    aiohttp.parsers.StreamWriter.set_tcp_cork = lambda s, v: True
    aiohttp.parsers.StreamWriter.set_tcp_nodelay = lambda s, v: True

    return client


def test_redirect_to_root(client):
    route = '/api/v{}'.format(version)
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
    route = '/api/v{}/version'.format(version)
    res = client.request(route, method='GET')
    assert res.json == {'version': gen.calc.entry['must']['dcos_version']}


def test_configure(client, mocker):
    route = '/api/v{}/configure'.format(version)
    featured_methods = {
        'GET': [200, 'application/json'],
        # Should return a 400 if validation has errors,
        # which this POST will return since the ssh_user
        # is an integer not a string.
        'POST': [400, 'application/json', '{"ssh_user": 1}'],
        'PUT': [405, 'text/plain'],
        'DELETE': [405, 'text/plain'],
        'HEAD': [405, 'text/plain'],
        'TRACE': [405, 'text/plain'],
        'CONNECT': [405, 'text/plain'],
    }
    mocked_get_config = mocker.patch('dcos_installer.backend.get_ui_config')
    mocked_create_config_from_post = mocker.patch('dcos_installer.backend.create_config_from_post')
    mocked_get_config.return_value = {"test": "config"}
    mocked_create_config_from_post.return_value = (True, None)

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
            assert res.json == {'test': 'config'}


def test_configure_status(client, mocker):
    route = '/api/v{}/configure/status'.format(version)
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

    mocked_do_validate_ssh_config = mocker.patch('dcos_installer.backend.do_validate_ssh_config')
    mocked_do_validate_ssh_config.return_value = {
        'ssh_user': 'error'
    }

    mocked_do_validate_gen_config = mocker.patch('dcos_installer.backend.do_validate_gen_config')
    mocked_do_validate_gen_config.return_value = {}

    for method, expected in featured_methods.items():
        res = client.request(route, method=method, expect_errors=True)
        assert res.status_code == expected[0], '{}: {}'.format(method, expected)
        assert res.content_type == expected[1], '{}: {}'.format(method, expected)


def test_success(client, mocker):
    route = '/api/v{}/success'.format(version)
    featured_methods = {
        'GET': [200, 'application/json'],
        'POST': [405, 'text/plain'],
        'PUT': [405, 'text/plain'],
        'DELETE': [405, 'text/plain'],
        'HEAD': [405, 'text/plain'],
        'TRACE': [405, 'text/plain'],
        'CONNECT': [405, 'text/plain'],
    }
    mocked_success = mocker.patch('dcos_installer.backend.success')
    mocked_success.return_value = {}, 200

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


def test_action_preflight(client, mocker):
    route = '/api/v{}/action/preflight'.format(version)

    mocked_read_json_state = mocker.patch('dcos_installer.async_server.read_json_state')

    mocked_get_config = mocker.patch('dcos_installer.backend.get_ui_config')
    mocked_get_config.return_value = {"test": "config"}

    mocked_run_preflight = mocker.patch('dcos_installer.action_lib.run_preflight')
    mocked_run_preflight.return_value = (i for i in range(10))

    mocked_read_json_state.side_effect = action_side_effect_return_config
    res = client.request(route, method='GET')
    assert res.json == {'preflight': {'mock_config': True}}

    mocked_read_json_state.side_effect = lambda x: {}
    res = client.request(route, method='GET')
    assert res.json == {}


def test_action_postflight(client, mocker):
    route = '/api/v{}/action/postflight'.format(version)

    mocked_read_json_state = mocker.patch('dcos_installer.async_server.read_json_state')

    mocked_get_config = mocker.patch('dcos_installer.backend.get_config')
    mocked_get_config.return_value = {"test": "config"}

    mocked_run_postflight = mocker.patch('dcos_installer.action_lib.run_postflight')
    mocked_run_postflight.return_value = (i for i in range(10))

    mocked_read_json_state.side_effect = action_side_effect_return_config
    res = client.request(route, method='GET')
    assert res.json == {'postflight': {'mock_config': True}}

    mocked_read_json_state.side_effect = lambda x: {}
    res = client.request(route, method='GET')
    assert res.json == {}


def test_action_deploy(client, mocker):
    route = '/api/v{}/action/deploy'.format(version)

    mocked_read_json_state = mocker.patch('dcos_installer.async_server.read_json_state')

    mocked_get_config = mocker.patch('dcos_installer.backend.get_config')
    mocked_get_config.return_value = {"test": "config"}

    mocked_install_dcos = mocker.patch('dcos_installer.action_lib.install_dcos')
    mocked_install_dcos.return_value = (i for i in range(10))

    mocked_read_json_state.side_effect = action_side_effect_return_config
    res = client.request(route, method='GET')
    assert res.json == {'deploy': {'mock_config': True}}

    mocked_read_json_state.side_effect = lambda x: {}
    res = client.request(route, method='GET')
    assert res.json == {}


def test_action_current(client):
    route = '/api/v{}/action/current'.format(version)
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


def test_configure_type(client, mocker):
    route = '/api/v{}/configure/type'.format(version)
    featured_methods = {
        'GET': [200, 'application/json'],
        'POST': [405, 'text/plain'],
        'PUT': [405, 'text/plain'],
        'DELETE': [405, 'text/plain'],
        'HEAD': [405, 'text/plain'],
        'TRACE': [405, 'text/plain'],
        'CONNECT': [405, 'text/plain'],
    }

    mocked_determine_config_type = mocker.patch('dcos_installer.backend.determine_config_type')
    mocked_determine_config_type.return_value = {}

    for method, expected in featured_methods.items():
        res = client.request(route, method=method, expect_errors=True)
        assert res.status_code == expected[0], '{}: {}'.format(
            method,
            expected)
        assert res.content_type == expected[1], '{}: {}'.format(
            method,
            expected)


def test_action_deploy_post(client, mocker):
    route = '/api/v{}/action/deploy'.format(version)

    mocked_read_json_state = mocker.patch('dcos_installer.async_server.read_json_state')

    mocked_get_config = mocker.patch('dcos_installer.backend.get_config')
    mocked_get_config.return_value = {
        'ssh_user': 'centos',
        'master_list': ['127.0.0.1'],
        'agent_list': ['127.0.0.2'],
        'public_agent_list': []
    }

    mocked_get_bootstrap_tarball = mocker.patch('dcos_installer.action_lib._get_bootstrap_tarball')
    mocked_get_bootstrap_tarball.return_value = '123'

    mocked_add_copy_packages = mocker.patch('dcos_installer.action_lib._add_copy_packages')

    # Deploy should be already executed for action 'deploy'
    mocked_read_json_state.side_effect = lambda arg: {
        'hosts': {
            '127.0.0.1': {
                'host_status': 'success'
            },
            '127.0.0.2': {
                'host_status': 'success'
            }
        }
    }
    res = client.request(route, method='POST')
    assert res.json == {'status': 'deploy was already executed, skipping'}

    # Test start deploy
    mocked_read_json_state.side_effect = lambda arg: False
    mocked_get_successful_nodes_from = mocker.patch('dcos_installer.action_lib.get_successful_nodes_from')
    mocked_get_successful_nodes_from.side_effect = lambda step, state_json_dir: [
        Node('127.0.0.1:22', tags={'role': 'master'})
    ]

    res = client.request(route, method='POST')
    assert res.json == {'status': 'deploy started'}
    assert mocked_add_copy_packages.call_count == 1


def test_action_deploy_retry(client, mocker):
    route = '/api/v{}/action/deploy'.format(version)

    mocked_read_json_state = mocker.patch('dcos_installer.async_server.read_json_state')

    mocked_get_config = mocker.patch('dcos_installer.backend.get_config')
    mocked_get_config.return_value = {
        'ssh_user': 'centos',
        'master_list': ['127.0.0.1'],
        'agent_list': ['127.0.0.2'],
        'public_agent_list': []
    }

    mocked_get_bootstrap_tarball = mocker.patch('dcos_installer.action_lib._get_bootstrap_tarball')
    mocked_get_bootstrap_tarball.return_value = '123'

    mocked_add_copy_packages = mocker.patch('dcos_installer.action_lib._add_copy_packages')
    mocked_remove_host = mocker.patch('dcos_installer.action_lib._remove_host')
    mocked_read_state_file = mocker.patch('dcos_installer.action_lib._read_state_file')

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

    mocked_read_json_state.side_effect = mocked_json_state
    res = client.post(route, params={'retry': 'true'}, content_type='application/x-www-form-urlencoded')
    assert res.json == {'details': ['127.0.0.1:22', '127.0.0.3:22022'], 'status': 'retried'}
    assert mocked_add_copy_packages.call_count == 1
    mocked_remove_host.assert_any_call('/genconf/state/deploy.json', '127.0.0.3:22022')
    mocked_remove_host.assert_any_call('/genconf/state/deploy.json', '127.0.0.1:22')
    assert mocked_remove_host.call_count == 2
    mocked_read_state_file.assert_called_with('/genconf/state/deploy.json')


def test_get_successful_nodes_from_fail(mocker):
    mocked_read_state_file = mocker.patch('dcos_installer.action_lib._read_state_file')
    mocked_read_state_file.return_value = {
        'hosts': {
            '10.10.0.1:22': {
                'host_status': 'success',
                'tags': {
                    'role': 'master'
                }
            },
            '10.10.0.2:22': {
                'host_status': 'failed',
                'tags': {
                    'role': 'master'
                }
            },
            '10.10.0.3:22': {
                'host_status': 'unstarted',
                'tags': {
                    'role': 'agent'
                }
            }
        }
    }

    with pytest.raises(Exception):
        action_lib.get_successful_nodes_from('preflight', '/genconf/states')


def test_get_successful_nodes_from(mocker):
    mocked_read_state_file = mocker.patch('dcos_installer.action_lib._read_state_file')
    mocked_read_state_file.return_value = {
        'hosts': {
            '10.10.0.1:22': {
                'host_status': 'success',
                'tags': {
                    'role': 'master'
                }
            },
            '10.10.0.2:22': {
                'host_status': 'failed',
                'tags': {
                    'role': 'agent'
                }
            },
            '10.10.0.3:22': {
                'host_status': 'unstarted',
                'tags': {
                    'role': 'agent'
                }
            }
        }
    }

    nodes = action_lib.get_successful_nodes_from('preflight', '/genconf/states')
    assert len(nodes) == 1
    assert nodes[0].ip == '10.10.0.1'


def test_get_full_nodes_list():
    config = {
        'master_list': ['10.10.0.1'],
        'ssh_port': 22022
    }
    nodes = action_lib.get_full_nodes_list(config)
    assert len(nodes) == 1
    assert nodes[0].ip == '10.10.0.1'
    assert nodes[0].port == 22022

    config = {
        'master_list': ['10.10.0.1', '10.10.0.2', '10.10.0.3']
    }
    nodes = action_lib.get_full_nodes_list(config)
    assert len(nodes) == 3
    assert nodes[0].port == 22


def test_nodes_count_by_type():
    targets = [
        Node('127.0.0.1', tags={'role': 'master'}),
        Node('127.0.0.2', tags={'role': 'master'}),
        Node('127.0.0.3', tags={'role': 'master'}),
        Node('127.0.0.4', tags={'role': 'agent'})
    ]

    assert action_lib.nodes_count_by_type(targets) == {
        'total_masters': 3,
        'total_agents': 1
    }
