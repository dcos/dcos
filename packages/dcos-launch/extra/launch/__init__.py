import launch.aws
import launch.azure
import launch.onprem
import launch.util


def get_launcher(config):
    """Returns the correct class of launcher from a validated launch config dict
    """
    platform = config['platform']
    provider = config['provider']
    if platform == 'aws':
        if provider == 'aws':
            return launch.aws.DcosCloudformationLauncher(config)
        if provider == 'onprem':
            return launch.onprem.OnpremLauncher(config)
    if platform == 'azure':
        return launch.azure.AzureResourceGroupLauncher(config)
    raise launch.util.LauncherError('UnsupportedAction', 'Launch platform not supported: {}'.format(platform))
