import json

import pytest
import yaml

import launch
import launch.cli
import launch.config
import launch.util
import pkgpanda.util
import test_util.aws


def check_cli(cmd):
    assert launch.cli.main(cmd) == 0, 'Command failed! {}'.format(' '.join(cmd))


def check_success(capsys, tmpdir, config_path):
    """
    Runs through the required functions of a launcher and then
    runs through the default usage of the script for a
    given config path and info path, ensuring each step passes
    if all steps finished successfully, this parses and returns the generated
    info JSON and stdout description JSON for more specific checks
    """
    # Test launcher directly first
    config = launch.config.get_validated_config(config_path)
    launcher = launch.get_launcher(config)
    info = launcher.create(config)
    launcher.wait(info)
    launcher.describe(info)
    launcher.test(info, 'py.test')
    launcher.delete(info)

    info_path = str(tmpdir.join('my_specific_info.json'))  # test non-default name

    # Now check launcher via CLI
    check_cli(['create', '--config-path={}'.format(config_path), '--info-path={}'.format(info_path)])
    # use the info written to disk to ensure JSON parsable
    info = pkgpanda.util.load_json(info_path)

    check_cli(['wait', '--info-path={}'.format(info_path)])

    # clear stdout capture
    capsys.readouterr()
    check_cli(['describe', '--info-path={}'.format(info_path)])
    # capture stdout from describe and ensure JSON parse-able
    description = json.loads(capsys.readouterr()[0])

    # general assertions about description
    assert 'masters' in description
    assert 'private_agents' in description
    assert 'public_agents' in description

    check_cli(['pytest', '--info-path={}'.format(info_path)])

    check_cli(['delete', '--info-path={}'.format(info_path)])

    return info, description


def test_aws_cf_simple(capsys, tmpdir, aws_cf_config_path):
    """Test that required parameters are consumed and appropriate output is generated
    """
    info, desc = check_success(capsys, tmpdir, aws_cf_config_path)
    # check AWS specific info
    assert 'stack_id' in info
    assert info['ssh_private_key'] == launch.util.MOCK_SSH_KEY_DATA
    # key should not have been generated
    assert 'key_name' not in info['temp_resources']


def test_aws_zen_cf_simple(capsys, tmpdir, aws_zen_cf_config_path):
    """Test that required parameters are consumed and appropriate output is generated
    """
    info, desc = check_success(capsys, tmpdir, aws_zen_cf_config_path)
    # check AWS specific info
    assert 'stack_id' in info
    assert 'vpc' in info['temp_resources']
    assert 'gateway' in info['temp_resources']
    assert 'private_subnet' in info['temp_resources']
    assert 'public_subnet' in info['temp_resources']


def mock_stack_not_found(*args):
    raise Exception('Mock stack was not found!!!')


def test_missing_aws_stack(aws_cf_config_path, monkeypatch):
    """ Tests that clean and appropriate errors will be raised
    """
    monkeypatch.setattr(test_util.aws, 'fetch_stack', mock_stack_not_found)
    config = launch.config.get_validated_config(aws_cf_config_path)
    assert 'platform' in config, str(config.items())
    aws_launcher = launch.get_launcher(config)

    def check_stack_error(cmd, args):
        with pytest.raises(launch.util.LauncherError) as exinfo:
            getattr(aws_launcher, cmd)(*args)
        assert exinfo.value.error == 'StackNotFound'

    info = aws_launcher.create(config)
    check_stack_error('wait', (info,))
    check_stack_error('describe', (info,))
    check_stack_error('delete', (info,))
    check_stack_error('test', (info, 'py.test'))


def test_key_helper(aws_cf_config_path):
    config = launch.config.get_validated_config(aws_cf_config_path)
    aws_launcher = launch.get_launcher(config)
    temp_resources = aws_launcher.key_helper(config)
    assert temp_resources['key_name'] == config['deployment_name']
    assert yaml.load(config['template_parameters'])['KeyName'] == config['deployment_name']
    assert config['ssh_private_key'] == launch.util.MOCK_SSH_KEY_DATA


def test_zen_helper(aws_zen_cf_config_path):
    config = launch.config.get_validated_config(aws_zen_cf_config_path)
    aws_launcher = launch.get_launcher(config)
    temp_resources = aws_launcher.zen_helper(config)
    assert temp_resources['vpc'] == launch.util.MOCK_VPC_ID
    assert temp_resources['gateway'] == launch.util.MOCK_GATEWAY_ID
    assert temp_resources['private_subnet'] == launch.util.MOCK_SUBNET_ID
    assert temp_resources['public_subnet'] == launch.util.MOCK_SUBNET_ID
    template_parameters = yaml.load(config['template_parameters'])
    assert template_parameters['Vpc'] == launch.util.MOCK_VPC_ID
    assert template_parameters['InternetGateway'] == launch.util.MOCK_GATEWAY_ID
    assert template_parameters['PrivateSubnet'] == launch.util.MOCK_SUBNET_ID
    assert template_parameters['PublicSubnet'] == launch.util.MOCK_SUBNET_ID
