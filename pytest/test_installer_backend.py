import json
import os
import subprocess

import passlib.hash

from dcos_installer import backend

os.environ["BOOTSTRAP_ID"] = "12345"


def test_password_hash():
    """Tests that the password hashing method creates de-cryptable hash
    """
    password = 'DcosTestingPassword!@#'
    # only reads from STDOUT
    hash_pw = subprocess.check_output(['dcos_installer', '--hash-password', password])
    hash_pw = hash_pw.decode('ascii').strip('\n')
    assert passlib.hash.sha512_crypt.verify(password, hash_pw), 'Hash does not match password'


def test_version(monkeypatch):
    monkeypatch.setenv('BOOTSTRAP_VARIANT', 'some-variant')
    version_data = subprocess.check_output(['dcos_installer', '--version']).decode()
    assert json.loads(version_data) == {
        'version': '1.8-dev',
        'variant': 'some-variant'
    }


def test_good_create_config_from_post(tmpdir):
    """
    Test that it creates the config
    """
    # Create a temp config
    workspace = tmpdir.strpath
    temp_config_path = workspace + '/config.yaml'
    temp_ip_detect_path = workspace + '/ip-detect'
    f = open(temp_ip_detect_path, "w")
    f.write("#/bin/bash foo")

    good_post_data = {
        "agent_list": ["10.0.0.2"],
        "master_list": ["10.0.0.1"],
        "cluster_name": "Good Test",
        "resolvers": ["4.4.4.4"],
        "ip_detect_filename": temp_ip_detect_path
    }
    expected_good_messages = {}

    err, msg = backend.create_config_from_post(
        post_data=good_post_data,
        config_path=temp_config_path)

    assert err is False
    assert msg == expected_good_messages


def test_bad_create_config_from_post(tmpdir):
    # Create a temp config
    workspace = tmpdir.strpath
    temp_config_path = workspace + '/config.yaml'

    bad_post_data = {
        "agent_list": "foo",
        "master_list": ["foo"],
    }
    expected_bad_messages = {
        "agent_list": 'agent_list must be a list',
        "master_list": 'Only IPv4 values are allowed. The following are invalid IPv4 addresses: foo',
    }
    err, msg = backend.create_config_from_post(
        post_data=bad_post_data,
        config_path=temp_config_path)
    assert err is True
    assert msg == expected_bad_messages


def test_do_validate_config(tmpdir):
    # Create a temp config
    workspace = tmpdir.strpath
    temp_config_path = workspace + '/config.yaml'

    expected_output = {
        'ssh_user': 'required parameter ssh_user was not provided',
        'master_list': 'required parameter master_list was not provided',
    }
    # remove num_masters and masters_quorum since they can change between runs
    messages = backend.do_validate_config(temp_config_path)
    assert messages['ssh_user'] == expected_output['ssh_user']
    assert messages['master_list'] == expected_output['master_list']


def test_get_config(tmpdir):
    # Create a temp config
    workspace = tmpdir.strpath
    temp_config_path = workspace + '/config.yaml'

    expected_file = """
{
    "cluster_name": "DC/OS",
    "master_discovery": "static",
    "exhibitor_storage_backend": "static",
    "resolvers": ["8.8.8.8","8.8.4.4"],
    "ssh_port": 22,
    "process_timeout": 10000,
    "bootstrap_url": "file:///opt/dcos_install_tmp"
}
    """
    config = backend.get_config(config_path=temp_config_path)
    expected_config = json.loads(expected_file)
    assert expected_config == config


def test_determine_config_type(tmpdir):
    # Create a temp config
    workspace = tmpdir.strpath
    temp_config_path = workspace + '/config.yaml'

    got_output = backend.determine_config_type(config_path=temp_config_path)
    expected_output = {
        'message': '',
        'type': 'minimal',
    }
    assert got_output == expected_output


def test_success():
    mock_config = {
        'master_list': ['10.0.0.1', '10.0.0.2', '10.0.0.5'],
        'agent_list': ['10.0.0.3', '10.0.0.4']
    }
    expected_output = {
        "success": "http://10.0.0.1",
        "master_count": 3,
        "agent_count": 2
    }
    expected_output_bad = {
        "success": "",
        "master_count": 0,
        "agent_count": 0
    }
    got_output, code = backend.success(mock_config)
    mock_config['master_list'] = None
    mock_config['agent_list'] = None
    bad_out, bad_code = backend.success(mock_config)

    assert got_output == expected_output
    assert code == 200
    assert bad_out == expected_output_bad
    assert bad_code == 400


def test_accept_overrides_for_undefined_config_params(tmpdir):
    temp_config_path = tmpdir.strpath + '/config.yaml'
    param = ('fake_test_param_name', 'fake_test_param_value')
    backend.create_config_from_post(
        post_data=dict([param]),
        config_path=temp_config_path)

    assert backend.get_config(config_path=temp_config_path)[param[0]] == param[1]
