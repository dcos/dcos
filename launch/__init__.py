import launch.aws
import test_util.aws


def get_launcher(config):
    """Returns the correct class of launcher from a validated launch config dict
    """
    platform = config['platform']
    if platform == 'aws':
        boto_wrapper = test_util.aws.BotoWrapper(
            config['aws_region'], config['aws_access_key_id'], config['aws_secret_access_key'])
        return launch.aws.AwsCloudformationLauncher(boto_wrapper)
    raise launch.util.LauncherError('UnsupportedAction', 'Launch platform not supported: {}'.format(platform))
