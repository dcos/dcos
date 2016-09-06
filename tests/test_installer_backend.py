import json
import os
import subprocess

import passlib.hash

from dcos_installer import backend
from dcos_installer.config import Config, make_default_config_if_needed, to_config

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

        # TODO(cmaloney): Add tests for the behavior around a non-existent config.yaml

        # Setting in a non-empty config.yaml which has no password set
        make_default_config_if_needed('genconf/config.yaml')
        assert 'superuser_password_hash' not in Config('genconf/config.yaml').config

        # Set the password
        subprocess.check_call(['dcos_installer', '--set-superuser-password', 'foo'], cwd=str(tmpdir))

        # Check that config.yaml has the password set
        config = Config('genconf/config.yaml')
        assert passlib.hash.sha512_crypt.verify('foo', config['superuser_password_hash'])


def test_version(monkeypatch):
    monkeypatch.setenv('BOOTSTRAP_VARIANT', 'some-variant')
    version_data = subprocess.check_output(['dcos_installer', '--version']).decode()
    assert json.loads(version_data) == {
        'version': '1.9-dev',
        'variant': 'some-variant'
    }


def test_good_create_config_from_post(tmpdir):
    """
    Test that it creates the config
    """
    # Create a temp config
    workspace = tmpdir.strpath
    temp_config_path = workspace + '/config.yaml'
    make_default_config_if_needed(temp_config_path)

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

    messages = backend.create_config_from_post(
        post_data=good_post_data,
        config_path=temp_config_path)

    assert messages == expected_good_messages


def test_bad_create_config_from_post(tmpdir):
    # Create a temp config
    workspace = tmpdir.strpath
    temp_config_path = workspace + '/config.yaml'
    make_default_config_if_needed(temp_config_path)

    bad_post_data = {
        "agent_list": "foo",
        "master_list": ["foo"],
    }
    expected_bad_messages = {
        "agent_list": "Must be a JSON formatted list, but couldn't be parsed the given value `foo` as "
                      "one because of: Expecting value: line 1 column 1 (char 0)",
        "master_list": 'Invalid IPv4 addresses in list: foo',
    }
    messages = backend.create_config_from_post(
        post_data=bad_post_data,
        config_path=temp_config_path)
    assert messages == expected_bad_messages


def test_do_validate_config(tmpdir):
    # Create a temp config
    genconf_dir = tmpdir.join('genconf')
    genconf_dir.ensure(dir=True)
    temp_config_path = str(genconf_dir.join('config.yaml'))

    # Initialize with defautls
    make_default_config_if_needed(temp_config_path)

    expected_output = {
        'ip_detect_contents': 'ip-detect script `genconf/ip-detect` must exist',
        'ssh_user': 'Must set ssh_user, no way to calculate value.',
        'master_list': 'Must set master_list, no way to calculate value.',
        'ssh_key_path': 'could not find ssh private key: genconf/ssh_key'
    }
    assert Config(config_path=temp_config_path).do_validate(include_ssh=True) == expected_output


def test_get_config(tmpdir):
    workspace = tmpdir.strpath
    temp_config_path = workspace + '/config.yaml'

    expected_data = {
        'cluster_name': 'DC/OS',
        'master_discovery': 'static',
        'exhibitor_storage_backend': 'static',
        'resolvers': ['8.8.8.8', '8.8.4.4'],
        'ssh_port': 22,
        'process_timeout': 10000
    }

    make_default_config_if_needed(temp_config_path)
    config = Config(temp_config_path)
    assert expected_data == config.config


def test_determine_config_type(tmpdir):
    # Ensure the default created config is of simple type
    workspace = tmpdir.strpath
    temp_config_path = workspace + '/config.yaml'
    make_default_config_if_needed(temp_config_path)
    got_output = backend.determine_config_type(config_path=temp_config_path)
    expected_output = {
        'message': '',
        'type': 'minimal',
    }
    assert got_output == expected_output


def test_success():
    mock_config = to_config({
        'master_list': ['10.0.0.1', '10.0.0.2', '10.0.0.5'],
        'agent_list': ['10.0.0.3', '10.0.0.4']
    })
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
    mock_config.update({'master_list': '', 'agent_list': ''})
    bad_out, bad_code = backend.success(mock_config)

    assert got_output == expected_output
    assert code == 200
    assert bad_out == expected_output_bad
    assert bad_code == 400


def test_accept_overrides_for_undefined_config_params(tmpdir):
    temp_config_path = tmpdir.strpath + '/config.yaml'
    param = ('fake_test_param_name', 'fake_test_param_value')
    make_default_config_if_needed(temp_config_path)
    messages = backend.create_config_from_post(
        post_data=dict([param]),
        config_path=temp_config_path)

    assert not messages, "unexpected validation error: {}".format(messages)
    assert Config(config_path=temp_config_path)[param[0]] == param[1]


simple_full_config = """---
cluster_name: DC/OS
master_discovery: static
exhibitor_storage_backend: static
master_list:
 - 127.0.0.1
bootstrap_url: http://example.com
"""


def test_do_configure(tmpdir):
    genconf_dir = tmpdir.join('genconf')
    genconf_dir.ensure(dir=True)
    config_path = genconf_dir.join('config.yaml')
    config_path.write(simple_full_config)
    genconf_dir.join('ip-detect').write('#!/bin/bash\necho 127.0.0.1')
    tmpdir.join('artifacts/bootstrap/12345.bootstrap.tar.xz').write('contents_of_bootstrap', ensure=True)
    tmpdir.join('artifacts/bootstrap/12345.active.json').write('{"active": "contents"}', ensure=True)

    with tmpdir.as_cwd():
        assert backend.do_configure(config_path=str(config_path)) == 0


aws_base_config = """---
# NOTE: Taking advantage of what isn't talked about not being validated so we don't need valid AWS /
# s3 credentials in this configuration.
aws_template_storage_bucket: psychic
aws_template_storage_bucket_path: mofo-the-gorilla
aws_template_storage_region_name: us-west-2
aws_template_upload: false
"""


def test_do_aws_configure(tmpdir, monkeypatch):
    monkeypatch.setenv('BOOTSTRAP_VARIANT', 'test_variant')
    genconf_dir = tmpdir.join('genconf')
    genconf_dir.ensure(dir=True)
    config_path = genconf_dir.join('config.yaml')
    config_path.write(aws_base_config)
    artifact_dir = tmpdir.join('artifacts/bootstrap')
    artifact_dir.ensure(dir=True)
    artifact_dir.join('12345.bootstrap.tar.xz').write("compressed_bootstrap_contents")
    artifact_dir.join('12345.active.json').write("['a-package']")
    artifact_dir.join('test_variant.bootstrap.latest').write("12345")
    tmpdir.join('artifacts/complete/test_variant.complete.latest.json').write('{"complete": "contents"}', ensure=True)

    with tmpdir.as_cwd():
        assert backend.do_aws_cf_configure() == 0
