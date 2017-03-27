import launch.aws
import launch.azure
import test_util.aws
import test_util.azure


def get_launcher(config):
    """Returns the correct class of launcher from a validated launch config dict
    """
    platform = config['platform']
    if platform == 'aws':
        return launch.aws.AwsCloudformationLauncher(test_util.aws.BotoWrapper(
            config['aws_region'], config['aws_access_key_id'], config['aws_secret_access_key']))
    if platform == 'azure':
        return launch.azure.AzureResourceGroupLauncher(test_util.azure.AzureWrapper(
            config['azure_location'], config['azure_subscription_id'], config['azure_client_id'],
            config['azure_client_secret'], config['azure_tenant_id']))
    raise launch.util.LauncherError('UnsupportedAction', 'Launch platform not supported: {}'.format(platform))
