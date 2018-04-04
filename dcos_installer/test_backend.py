import json
import logging
import os
import subprocess
import textwrap
import uuid

import boto3
import passlib.hash
import pytest

import pkgpanda.util
from dcos_installer import backend
from dcos_installer.config import Config, make_default_config_if_needed, to_config

os.environ["BOOTSTRAP_ID"] = "12345"


def test_password_hash():
    """Tests that the password hashing method creates de-cryptable hash
    """
    password = 'DcosTestingPassword!@#'
    # only reads from STDOUT
    hash_pw = subprocess.check_output(['dcos_installer', '--hash-password', password])
    print(hash_pw)
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
        create_fake_build_artifacts(tmpdir)
        subprocess.check_call(['dcos_installer', '--set-superuser-password', 'foo'], cwd=str(tmpdir))

        # Check that config.yaml has the password set
        config = Config('genconf/config.yaml')
        assert passlib.hash.sha512_crypt.verify('foo', config['superuser_password_hash'])


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="test fails on Windows reason unknown")
def test_generate_node_upgrade_script(tmpdir, monkeypatch):
    upgrade_config = """
---
# The name of your DC/OS cluster. Visable in the DC/OS user interface.
cluster_name: 'DC/OS'
master_discovery: static
exhibitor_storage_backend: 'static'
resolvers:
- 8.8.8.8
- 8.8.4.4
ssh_port: 22
process_timeout: 10000
bootstrap_url: file:///opt/dcos_install_tmp
master_list: ['10.0.0.1', '10.0.0.2', '10.0.0.5']
"""
    monkeypatch.setenv('BOOTSTRAP_VARIANT', '')
    create_config(upgrade_config, tmpdir)
    create_fake_build_artifacts(tmpdir)

    output = subprocess.check_output(['dcos_installer', '--generate-node-upgrade-script', 'fake'], cwd=str(tmpdir))
    assert output.decode('utf-8').splitlines()[-1].split("Node upgrade script URL: ", 1)[1]\
                                                  .endswith("dcos_node_upgrade.sh")

    try:
        subprocess.check_output(['dcos_installer', '--generate-node-upgrade-script'], cwd=str(tmpdir))
    except subprocess.CalledProcessError as e:
        print(e.output)
        assert e.output.decode('ascii') == "Must provide the version of the cluster upgrading from\n"
    else:
        raise Exception("Test passed, this should not pass without specifying a version number")


def test_version(monkeypatch):
    monkeypatch.setenv('BOOTSTRAP_VARIANT', 'some-variant')
    version_data = subprocess.check_output(['dcos_installer', '--version']).decode()
    assert json.loads(version_data) == {
        'version': '1.12-dev',
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

    create_fake_build_artifacts(tmpdir)
    with tmpdir.as_cwd():
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

    create_fake_build_artifacts(tmpdir)
    with tmpdir.as_cwd():
        messages = backend.create_config_from_post(
            post_data=bad_post_data,
            config_path=temp_config_path)

    assert messages == expected_bad_messages


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Code tests linux configuration")
def test_do_validate_config(tmpdir, monkeypatch):
    monkeypatch.setenv('BOOTSTRAP_VARIANT', 'test_variant')

    # Create a temp config
    genconf_dir = tmpdir.join('genconf')
    genconf_dir.ensure(dir=True)
    temp_config_path = str(genconf_dir.join('config.yaml'))

    # Initialize with defautls
    make_default_config_if_needed(temp_config_path)

    create_fake_build_artifacts(tmpdir)
    expected_output = {
        'ip_detect_contents': 'ip-detect script `genconf/ip-detect` must exist',
        'ssh_user': 'Must set ssh_user, no way to calculate value.',
        'master_list': 'Must set master_list, no way to calculate value.',
        'ssh_key_path': 'could not find ssh private key: genconf/ssh_key'
    }
    with tmpdir.as_cwd():
        assert Config(config_path='genconf/config.yaml').do_validate(include_ssh=True) == expected_output


def test_get_config(tmpdir):
    workspace = tmpdir.strpath
    temp_config_path = workspace + '/config.yaml'

    expected_data = {
        'cluster_name': 'DC/OS',
        'master_discovery': 'static',
        'exhibitor_storage_backend': 'static',
        'resolvers': ['8.8.8.8', '8.8.4.4'],
        'ssh_port': 22,
        'process_timeout': 10000,
        'bootstrap_url': 'file:///opt/dcos_install_tmp'
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
    create_fake_build_artifacts(tmpdir)
    with tmpdir.as_cwd():
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


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="test fails on Windows reason unknown")
def test_do_configure(tmpdir, monkeypatch):
    monkeypatch.setenv('BOOTSTRAP_VARIANT', 'test_variant')
    create_config(simple_full_config, tmpdir)
    create_fake_build_artifacts(tmpdir)
    with tmpdir.as_cwd():
        assert backend.do_configure(config_path='genconf/config.yaml') == 0


aws_base_config = """---
# NOTE: Taking advantage of what isn't talked about not being validated so we don't need valid AWS /
# s3 credentials in this configuration.
aws_template_storage_bucket: psychic
aws_template_storage_bucket_path: mofo-the-gorilla
aws_template_storage_region_name: us-west-2
aws_template_upload: false
"""


def test_do_aws_configure(release_config_aws, tmpdir, monkeypatch):
    monkeypatch.setenv('BOOTSTRAP_VARIANT', 'test_variant')
    create_config(aws_base_config, tmpdir)
    create_fake_build_artifacts(tmpdir)

    with tmpdir.as_cwd():
        assert backend.do_aws_cf_configure() == 0


@pytest.fixture
def valid_storage_config(release_config_aws):
    """ Uses the settings from dcos-release.config.yaml ['testing'] to create a
    new upload and then deletes it when the test is over
    """
    s3_bucket_name = release_config_aws['bucket']
    bucket_path = str(uuid.uuid4())
    yield """---
master_list:
 - 127.0.0.1
aws_template_storage_bucket: {bucket}
aws_template_storage_bucket_path: {bucket_path}
aws_template_upload: true
""".format(
        bucket=release_config_aws['bucket'],
        bucket_path=bucket_path)
    session = boto3.session.Session()
    s3 = session.resource('s3')
    s3_bucket = s3.Bucket(s3_bucket_name)
    for o in s3_bucket.objects.filter(Prefix=bucket_path):
        o.delete()


def test_do_aws_cf_configure_valid_storage_config(release_config_aws, valid_storage_config, tmpdir, monkeypatch):
    assert aws_cf_configure(valid_storage_config, tmpdir, monkeypatch) == 0
    # TODO: add an assertion that the config that was resolved inside do_aws_cf_configure
    # ended up with the correct region where the above testing bucket was created.


def test_override_aws_template_storage_region_name(release_config_aws, valid_storage_config, tmpdir, monkeypatch):
    config_str = valid_storage_config
    config_str += '\naws_template_storage_region_name: {}'.format(os.environ['AWS_DEFAULT_REGION'])
    assert aws_cf_configure(config_str, tmpdir, monkeypatch) == 0


def aws_cf_configure(config, tmpdir, monkeypatch):
    monkeypatch.setenv('BOOTSTRAP_VARIANT', 'test_variant')

    create_config(config, tmpdir)
    create_fake_build_artifacts(tmpdir)
    with tmpdir.as_cwd():
        return backend.do_aws_cf_configure()


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="test fails on Windows reason unknown")
def test_do_configure_valid_config_no_duplicate_logging(tmpdir, monkeypatch, caplog):
    """
    Log messages are logged exactly once.
    """
    monkeypatch.setenv('BOOTSTRAP_VARIANT', 'test_variant')
    create_config(simple_full_config, tmpdir)
    create_fake_build_artifacts(tmpdir)
    with tmpdir.as_cwd():
        assert backend.do_configure(config_path='genconf/config.yaml') == 0

    # The message comes from gen.get_dcosconfig_source_target_and_templates() function
    expected_message = 'Generating configuration files...'
    filtered_messages = [rec.message for rec in caplog.records if rec.message == expected_message]
    assert [expected_message] == filtered_messages


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="test fails on Windows reason unknown")
def test_do_configure_logs_validation_errors(tmpdir, monkeypatch, caplog):
    """
    Configuration validation errors are logged as `error` messages.
    """
    monkeypatch.setenv('BOOTSTRAP_VARIANT', 'test_variant')
    invalid_config = textwrap.dedent("""---
    cluster_name: DC/OS
    master_discovery: static
    # Remove `exhibitor_storage_backend` from configuration
    # exhibitor_storage_backend: static
    master_list:
    - 127.0.0.1
    bootstrap_url: http://example.com
    """)
    create_config(invalid_config, tmpdir)
    create_fake_build_artifacts(tmpdir)
    with tmpdir.as_cwd():
        assert backend.do_configure(config_path='genconf/config.yaml') == 1

    expected_error_message = (
        'exhibitor_storage_backend: Must set exhibitor_storage_backend, '
        'no way to calculate value.'
    )
    error_logs = [rec for rec in caplog.records if rec.message == expected_error_message]
    assert len(error_logs) == 1

    error_log = error_logs[0]
    assert error_log.levelno == logging.ERROR


def create_config(config_str, tmpdir):
    genconf_dir = tmpdir.join('genconf')
    genconf_dir.ensure(dir=True)
    config_path = genconf_dir.join('config.yaml')
    config_path.write(config_str)
    genconf_dir.join('ip-detect').write('#!/bin/bash\necho 127.0.0.1')


def create_fake_build_artifacts(tmpdir):
    artifact_dir = tmpdir.join('artifacts/bootstrap')
    artifact_dir.ensure(dir=True)
    artifact_dir.join('12345.bootstrap.tar.xz').write('contents_of_bootstrap', ensure=True)
    artifact_dir.join('12345.active.json').write('["package--version"]', ensure=True)
    artifact_dir.join('test_variant.bootstrap.latest').write("12345")
    tmpdir.join('artifacts/complete/test_variant.complete.latest.json').write(
        '{"bootstrap": "12345", "packages": ["package--version"]}',
        ensure=True,
    )
    tmpdir.join('artifacts/complete/complete.latest.json').write(
        '{"bootstrap": "12345", "packages": ["package--version"]}',
        ensure=True,
    )
    tmpdir.join('artifacts/packages/package/package--version.tar.xz').write('contents_of_package', ensure=True)
