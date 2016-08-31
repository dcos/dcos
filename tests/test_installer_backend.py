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


def test_set_superuser_password(tmpdir):
    """Test that --set-superuser-hash works"""

    with tmpdir.as_cwd():
        tmpdir.join('genconf').ensure(dir=True)
        # check config.yaml doesn't have the password
        assert 'superuser_password_hash' not in backend.get_config('genconf/config.yaml')

        # Set the password
        subprocess.check_call(['dcos_installer', '--set-superuser-password', 'foo'], cwd=str(tmpdir))

        # Check that config.yaml has the password set
        config = backend.get_config('genconf/config.yaml')
        assert passlib.hash.sha512_crypt.verify('foo', config['superuser_password_hash'])


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
        "agent_list": "Must be a JSON formatted list, but couldn't be parsed the given value `foo` as "
                      "one because of: Expecting value: line 1 column 1 (char 0)",
        "master_list": 'Invalid IPv4 addresses in list: foo',
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
        'ssh_user': 'Must set ssh_user, no way to calculate value.',
        'master_list': 'Must set master_list, no way to calculate value.',
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
    validation_err, data = backend.create_config_from_post(
        post_data=dict([param]),
        config_path=temp_config_path)

    assert not validation_err, "unexpected validation error: {}".format(data)
    assert backend.get_config(config_path=temp_config_path)[param[0]] == param[1]


simple_full_config = """---
master_list:
 - 127.0.0.1
"""


def test_do_configure(tmpdir):
    genconf_dir = tmpdir.join('genconf')
    genconf_dir.ensure(dir=True)
    config_path = genconf_dir.join('config.yaml')
    config_path.write(simple_full_config)
    genconf_dir.join('ip-detect').write('#!/bin/bash\necho 127.0.0.1')
    tmpdir.join('artifacts/12345.bootstrap.tar.xz').write('contents_of_bootstrap', ensure=True)
    tmpdir.join('artifacts/12345.active.json').write('{"active": "contents"}', ensure=True)

    with tmpdir.as_cwd():
        assert backend.do_configure(config_path=str(config_path)) == 0
