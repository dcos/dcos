import json
import operator
import os
from shutil import copytree

import pytest

from pkgpanda.http import app
from pkgpanda.util import is_windows, resources_test_dir


def assert_response(response, status_code, body, headers=None, body_cmp=operator.eq):
    """Assert response has the expected status_code, body, and headers.

    body_cmp is a callable that takes the response body and expected body and
    returns a boolean stating whether the comparison succeeds.

        body_cmp(response.data, body)

    """
    headers = headers or {}

    assert response.status_code == status_code, (
        'Expected status code {}, got {}'.format(status_code, response.status_code)
    )

    for header, value in headers.items():
        response_value = response.headers.get(header)
        assert response_value == value, (
            'Expected {} header value {}, got {}'.format(header, value, response_value)
        )

    assert body_cmp(response.data, body), 'Unexpected response body'


def assert_json_response(response, status_code, body, headers=None, body_cmp=operator.eq):
    """Assert JSON response has the expected status_code, body, and headers.

    Asserts that the response's content-type is application/json.

    body_cmp is a callable that takes the JSON-decoded response body and
    expected body and returns a boolean stating whether the comparison
    succeeds.

        body_cmp(json.loads(response.data.decode('utf-8')), body)

    """
    headers = dict(headers or {})
    headers['Content-Type'] = 'application/json'

    def json_cmp(response_body, body):
        return body_cmp(json.loads(response_body.decode('utf-8')), body)

    assert_response(response, status_code, body, headers, json_cmp)


def assert_error(response, status_code, headers=None, **kwargs):
    """Assert error response has the expected status_code and kwargs.

    Asserts that the response body is a JSON object containing an error message
    and all provided kwargs.

    If error is not passed as a kwarg, only the presence of an error message
    will be asserted, not its content.

    """
    headers = headers or {}

    def error_cmp(response_body, body):
        return (
            # response_body is a json object.
            isinstance(response_body, dict) and
            # response_body has all keys in body as well as an error message.
            set(response_body.keys()) == set(list(body.keys()) + ['error']) and
            # response_body has all values in body.
            all(response_body.get(k) == v for k, v in body.items())
        )

    assert_json_response(response, status_code, kwargs, headers, error_cmp)


def _set_test_config(app):
    app.config['TESTING'] = True
    app.config['DCOS_ROOT'] = resources_test_dir('install')
    app.config['DCOS_STATE_DIR_ROOT'] = resources_test_dir('install/package_state')
    app.config['DCOS_REPO_DIR'] = resources_test_dir('packages')


@pytest.mark.skipif(is_windows, reason="test fails on Windows reason unknown")
def test_list_packages():
    _set_test_config(app)
    client = app.test_client()
    assert_json_response(client.get('/repository/'), 200, [
        'mesos--0.22.0',
        'mesos--0.23.0',
        'mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8',
        'mesos-config--justmesos',
    ])


@pytest.mark.skipif(is_windows, reason="test fails on Windows reason unknown")
def test_get_package():
    _set_test_config(app)
    client = app.test_client()

    assert_json_response(client.get('/repository/mesos--0.22.0'), 200, {
        'id': 'mesos--0.22.0',
        'name': 'mesos',
        'version': '0.22.0',
    })

    # Get nonexistent package.
    assert_error(client.get('/repository/nonexistent-package--fakeversion'), 404)
    assert_error(client.get('/repository/package---version'), 404)
    assert_error(client.get('/repository/packageversion'), 404)
    assert_error(client.get('/repository/!@#*'), 404)


@pytest.mark.skipif(is_windows, reason="test fails on Windows reason unknown")
def test_list_active_packages():
    _set_test_config(app)
    client = app.test_client()
    packages = json.loads(client.get('/active/').data.decode('utf-8'))
    assert packages == [
        'mesos--0.22.0',
        'mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8']


@pytest.mark.skipif(is_windows, reason="test fails on Windows reason unknown")
def test_get_active_package():
    _set_test_config(app)
    client = app.test_client()

    assert_json_response(client.get('/active/mesos--0.22.0'), 200, {
        'id': 'mesos--0.22.0',
        'name': 'mesos',
        'version': '0.22.0',
    })

    # Get nonexistent package.
    assert_error(client.get('/active/mesos--0.23.0'), 404)
    assert_error(client.get('/active/package---version'), 404)
    assert_error(client.get('/active/packageversion'), 404)
    assert_error(client.get('/active/!@#*'), 404)


@pytest.mark.skipif(is_windows, reason="test fails on Windows reason unknown")
def test_activate_packages(tmpdir):
    _set_test_config(app)
    install_dir = str(tmpdir.join('install'))
    copytree(resources_test_dir('install'), install_dir, symlinks=True)
    app.config['DCOS_ROOT'] = install_dir
    app.config['DCOS_ROOTED_SYSTEMD'] = True
    client = app.test_client()

    # Upgrade from mesos--0.22.0 to mesos--0.23.0.
    old_packages = [
        'mesos--0.22.0',
        'mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8',
    ]
    new_packages = [
        'mesos--0.23.0',
        'mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8',
    ]
    assert_json_response(client.get('/active/'), 200, old_packages)
    assert_response(
        client.put(
            '/active/',
            content_type='application/json',
            data=json.dumps(new_packages),
        ),
        204,
        b'',
    )
    assert_json_response(client.get('/active/'), 200, new_packages)

    # mesos--0.23.0 expects to have a state directory.
    assert os.path.isdir(app.config['DCOS_STATE_DIR_ROOT'] + '/mesos')

    # Attempt to activate nonexistent packages.
    nonexistent_packages = [
        'nonexistent-package--fakeversion1',
        'nonexistent-package--fakeversion2',
    ]
    assert_error(
        client.put(
            '/active/',
            content_type='application/json',
            data=json.dumps(['mesos--0.23.0'] + nonexistent_packages),
        ),
        409,
        missing_packages=sorted(nonexistent_packages),
    )


@pytest.mark.skipif(is_windows, reason="test fails on Windows reason unknown")
def test_fetch_package(tmpdir):
    _set_test_config(app)
    client = app.test_client()
    app.config['DCOS_REPO_DIR'] = str(tmpdir)

    # Successful package fetch.
    assert_json_response(client.get('/repository/'), 200, [])
    assert_response(
        client.post(
            '/repository/mesos--0.22.0',
            content_type='application/json',
            data=json.dumps({
                'repository_url': 'file://{}/{}/'.format(os.getcwd(), resources_test_dir('remote_repo'))
            }),
        ),
        204,
        b'',
    )
    assert_json_response(client.get('/repository/'), 200, ['mesos--0.22.0'])

    # No repository URL provided.
    assert_error(
        client.post(
            '/repository/mesos--0.23.0',
            content_type='application/json',
            data=json.dumps({}),
        ),
        400,
    )

    # Invalid package ID.
    assert_error(
        client.post(
            '/repository/invalid---package',
            content_type='application/json',
            data=json.dumps({
                'repository_url': 'file://{}/'.format(resources_test_dir('remote_repo'))
            }),
        ),
        400,
    )


@pytest.mark.skipif(is_windows, reason="test fails on Windows reason unknown")
def test_remove_package(tmpdir):
    _set_test_config(app)
    repo_dir = str(tmpdir.join('repo'))
    copytree(resources_test_dir('packages'), repo_dir)
    app.config['DCOS_REPO_DIR'] = repo_dir
    client = app.test_client()

    # Successful deletion.
    package_to_delete = 'mesos--0.23.0'
    assert_json_response(
        client.get('/repository/'),
        200,
        package_to_delete,
        body_cmp=lambda response_body, package: package in response_body,
    )
    assert_response(client.delete('/repository/' + package_to_delete), 204, b'')
    assert_json_response(
        client.get('/repository/'),
        200,
        package_to_delete,
        body_cmp=lambda response_body, package: package not in response_body,
    )

    # Attempted deletion of active package.
    package_to_delete = 'mesos--0.22.0'
    assert_json_response(
        client.get('/active/'),
        200,
        package_to_delete,
        body_cmp=lambda response_body, package: package in response_body,
    )
    assert_error(client.delete('/repository/' + package_to_delete), 409)
    assert_json_response(
        client.get('/active/'),
        200,
        package_to_delete,
        body_cmp=lambda response_body, package: package in response_body,
    )

    # Attempted deletion of nonexistent package.
    assert_error(client.delete('/repository/nonexistent-package--fakeversion'), 404)
    assert_error(client.delete('/repository/invalid---package'), 404)
