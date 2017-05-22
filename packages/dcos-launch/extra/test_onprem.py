import launch


def test_aws_onprem(check_cli_success, aws_onprem_config_path):
    info, desc = check_cli_success(aws_onprem_config_path)
    assert 'stack_id' in info
    assert info['ssh_private_key'] == launch.util.MOCK_SSH_KEY_DATA
    assert 'template_body' not in desc  # distracting irrelevant information


def test_aws_onprem_with_helper(check_cli_success, aws_onprem_with_helper_config_path):
    info, desc = check_cli_success(aws_onprem_with_helper_config_path)
    assert 'stack_id' in info
    assert info['ssh_private_key'] == launch.util.MOCK_SSH_KEY_DATA
    assert 'template_body' not in desc  # distracting irrelevant information
    assert 'KeyName' in info['template_parameters']
