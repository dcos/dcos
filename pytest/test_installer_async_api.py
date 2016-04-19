import aiohttp
from dcos_installer.async_server import app
from webtest_aiohttp import TestApp

version = 1
client = TestApp(app)
client.expect_errors = False


def test_redirect_to_root(monkeypatch):
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_cork', lambda s, v: True)
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_nodelay', lambda s, v: True)
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


def test_configure(monkeypatch, mocker):
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_cork', lambda s, v: True)
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_nodelay', lambda s, v: True)
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


def test_configure_status(monkeypatch, mocker):
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_cork', lambda s, v: True)
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_nodelay', lambda s, v: True)
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


def test_success(monkeypatch, mocker):
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_cork', lambda s, v: True)
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_nodelay', lambda s, v: True)
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


def test_action_preflight(monkeypatch, mocker):
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_cork', lambda s, v: True)
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_nodelay', lambda s, v: True)
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


def test_action_postflight(monkeypatch, mocker):
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_cork', lambda s, v: True)
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_nodelay', lambda s, v: True)
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


def test_action_deploy(monkeypatch, mocker):
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_cork', lambda s, v: True)
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_nodelay', lambda s, v: True)
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


def test_action_current(monkeypatch):
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_cork', lambda s, v: True)
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_nodelay', lambda s, v: True)
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


def test_configure_type(monkeypatch, mocker):
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_cork', lambda s, v: True)
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_nodelay', lambda s, v: True)
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


def test_action_deploy_post(monkeypatch, mocker):
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_cork', lambda s, v: True)
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_nodelay', lambda s, v: True)
    route = '/api/v{}/action/deploy'.format(version)

    mocked_read_json_state = mocker.patch('dcos_installer.async_server.read_json_state')

    mocked_get_config = mocker.patch('dcos_installer.backend.get_config')
    mocked_get_config.return_value = {
        'ssh_user': 'centos',
        'master_list': ['127.0.0.1'],
        'agent_list': ['127.0.0.2']
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
    res = client.request(route, method='POST')
    assert res.json == {'status': 'deploy started'}
    assert mocked_add_copy_packages.call_count == 1


def test_action_deploy_retry(monkeypatch, mocker):
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_cork', lambda s, v: True)
    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_nodelay', lambda s, v: True)
    route = '/api/v{}/action/deploy'.format(version)

    mocked_read_json_state = mocker.patch('dcos_installer.async_server.read_json_state')

    mocked_get_config = mocker.patch('dcos_installer.backend.get_config')
    mocked_get_config.return_value = {
        'ssh_user': 'centos',
        'master_list': ['127.0.0.1'],
        'agent_list': ['127.0.0.2']
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
                    'host_status': 'failed'
                },
                '127.0.0.2:22022': {
                    'host_status': 'success'
                },
                '127.0.0.3:22022': {
                    'host_status': 'failed'
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


# def test_logs(monkeypatch):
#    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_cork', lambda s, v: True)
#    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_nodelay', lambda s, v: True)
#    route = '/api/v{}/logs'.format(version)

# def test_serve_assets(monkeypatch):
#    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_cork', lambda s, v: True)
#    monkeypatch.setattr(aiohttp.parsers.StreamWriter, 'set_tcp_nodelay', lambda s, v: True)
#    route = '/api/v{}/assets'.format(version)
#    featured_methods = {
#        'GET': [200],
#        'POST': [405, 'text/plain'],
#        'PUT': [405, 'text/plain'],
#        'DELETE': [405, 'text/plain'],
#        'HEAD': [405, 'text/plain'],
#        'TRACE': [405, 'text/plain'],
#        'CONNECT': [405, 'text/plain']
#    }
#    filetypes = {
#        '.js': 'application/javascript',
#        '.json': 'application/json',
#        '.txt': 'text/plain'
#    }
#    for method, expected in featured_methods.items():
#       res = client.request(route, method=method, expect_errors=True)
#       assert res.status_code == expected[0], '{}: {}'.format(method, expected)
