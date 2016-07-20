import json
import os
from shutil import copytree

from pkgpanda.http import app


def _set_test_config(app):
    app.config['TESTING'] = True
    app.config['DCOS_ROOT'] = '../tests/resources/install'
    app.config['DCOS_REPO_DIR'] = '../tests/resources/packages'


def test_list_packages():
    _set_test_config(app)
    client = app.test_client()
    packages = json.loads(client.get('/').data.decode('utf-8'))
    assert packages == [
        'mesos--0.22.0',
        'mesos--0.23.0',
        'mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8',
        'mesos-config--justmesos']


def test_get_package():
    _set_test_config(app)
    client = app.test_client()
    assert client.get('/mesos--0.22.0').status_code == 204
    assert client.get('/nonexistent-package--fakeversion').status_code == 404


def test_list_active_packages():
    _set_test_config(app)
    client = app.test_client()
    packages = json.loads(client.get('/active/').data.decode('utf-8'))
    assert packages == [
        'mesos--0.22.0',
        'mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8']


def test_get_active_package():
    _set_test_config(app)
    client = app.test_client()
    assert client.get('/active/mesos--0.22.0').status_code == 204
    assert client.get('/active/mesos--0.23.0').status_code == 404


def test_activate_packages(tmpdir):
    _set_test_config(app)
    install_dir = str(tmpdir.join('install'))
    copytree('../tests/resources/install', install_dir, symlinks=True)
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
    assert json.loads(client.get('/active/').data.decode('utf-8')) == old_packages
    assert client.put(
        '/active/',
        content_type='application/json',
        data=json.dumps(new_packages),
    ).status_code == 204
    assert json.loads(client.get('/active/').data.decode('utf-8')) == new_packages

    # Attempt to activate nonexistent package.
    assert client.put(
        '/active/',
        content_type='application/json',
        data=json.dumps(['nonexistent-package--fakeversion']),
    ).status_code == 409


def test_fetch_package(tmpdir):
    _set_test_config(app)
    client = app.test_client()
    app.config['DCOS_REPO_DIR'] = str(tmpdir)

    # Successful package fetch.
    assert json.loads(client.get('/').data.decode('utf-8')) == []
    assert client.post(
        '/mesos--0.22.0',
        content_type='application/json',
        data=json.dumps({
            'repository_url': 'file://{}/../tests/resources/remote_repo'.format(os.getcwd())
        }),
    ).status_code == 204
    assert json.loads(client.get('/').data.decode('utf-8')) == ['mesos--0.22.0']

    # No repository URL provided.
    assert client.post(
        '/mesos--0.23.0',
        content_type='application/json',
        data=json.dumps({}),
    ).status_code == 400


def test_remove_package(tmpdir):
    _set_test_config(app)
    repo_dir = str(tmpdir.join('repo'))
    copytree('../tests/resources/packages', repo_dir)
    app.config['DCOS_REPO_DIR'] = repo_dir
    client = app.test_client()

    # Successful deletion.
    package_to_delete = 'mesos--0.23.0'
    assert package_to_delete in json.loads(client.get('/').data.decode('utf-8'))
    assert client.delete('/' + package_to_delete).status_code == 204
    assert package_to_delete not in json.loads(client.get('/').data.decode('utf-8'))

    # Attempted deletion of active package.
    package_to_delete = 'mesos--0.22.0'
    assert package_to_delete in json.loads(client.get('/active/').data.decode('utf-8'))
    assert client.delete('/' + package_to_delete).status_code == 409
    assert package_to_delete in json.loads(client.get('/active/').data.decode('utf-8'))

    # Attempted deletion of nonexistent package.
    assert client.delete('/nonexistent-package--fakeversion').status_code == 404
