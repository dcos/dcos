import launch.aws
import launch.azure


def get_launcher(config):
    """Returns the correct class of launcher from a validated launch config dict
    """
    platform = config['platform']
    if platform == 'aws':
        return launch.aws.AwsCloudformationLauncher(config)
    if platform == 'azure':
        return launch.azure.AzureResourceGroupLauncher(config)
    raise launch.util.LauncherError('UnsupportedAction', 'Launch platform not supported: {}'.format(platform))
