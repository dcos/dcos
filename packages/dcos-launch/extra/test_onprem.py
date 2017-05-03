import launch


def test_aws_onprem(check_cli_success, aws_onprem_config_path):
    info, desc = check_cli_success(aws_onprem_config_path)
    assert 'stack_id' in info
    assert info['ssh_private_key'] == launch.util.MOCK_SSH_KEY_DATA
    assert 'onprem_dcos_config_contents' in info  # needs to be in info for provisioning
    assert 'template_body' not in desc  # distracting irrelevant information
    assert 'dcos_config' in desc  # check for the re-formatted fields


def test_aws_onprem_with_helper(check_cli_success, aws_onprem_with_helper_config_path):
    info, desc = check_cli_success(aws_onprem_with_helper_config_path)
    assert 'stack_id' in info
    assert info['ssh_private_key'] == launch.util.MOCK_SSH_KEY_DATA
    assert 'onprem_dcos_config_contents' in info  # needs to be in info for provisioning
    assert 'template_body' not in desc  # distracting irrelevant information
    assert 'dcos_config' in desc  # check for the re-formatted fields
    assert 'KeyName' in info['template_parameters']
