def test_azure_template(check_cli_success, azure_config_path):
    info, desc = check_cli_success(azure_config_path)


def test_azure_template_with_helper(check_cli_success, azure_with_helper_config_path):
    info, desc = check_cli_success(azure_with_helper_config_path)
