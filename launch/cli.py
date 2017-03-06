"""DC/OS Launch

Usage:
  dcos-launch create [-L LEVEL -c PATH -i PATH]
  dcos-launch wait [-L LEVEL -i PATH]
  dcos-launch describe [-L LEVEL -i PATH]
  dcos-launch pytest [-L LEVEL -i PATH -e LIST] [--] [<pytest_extras>]...
  dcos-launch delete [-L LEVEL -i PATH]

Commands:
  create    Reads the file given by --config-path, creates the cluster
              described therein and finally dumps a JSON file to the path
              given in --info-path which can then be used with the wait,
              describe, pytest, and delete calls.
  wait      Block until the cluster is up and running.
  describe  Return additional information about the composition of the cluster.
  pytest    Runs integration test suite on cluster. Can optionally supply
              options and arguments to pytest
  delete    Destroying the provided cluster deployment.

Options:
  -c PATH --config-path=PATH
            Path for config to create cluster from [default: config.yaml].
  -i PATH --info-path=PATH
            JSON file output by create and consumed by wait, describe,
            and delete [default: cluster_info.json].
  -e LIST --env=LIST
            Specifies a comma-delimited list of environment variables to be
            passed from the local environment into the test environment.
  -L LEVEL --log-level=LEVEL
            One of: critical, error, warning, info, debug, and trace
            [default: info].
"""
import logging
import os
import sys

from docopt import docopt

import launch
import launch.config
import launch.util
from pkgpanda.util import json_prettyprint, load_json, write_json

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'


def _handle_logging(log_level_str):
    if log_level_str == 'CRITICAL':
        log_level = logging.CRITICAL
    elif log_level_str == 'ERROR':
        log_level = logging.ERROR
    elif log_level_str == 'WARNING':
        log_level = logging.WARNING
    elif log_level_str == 'INFO':
        log_level = logging.INFO
    elif log_level_str == 'DEBUG' or log_level_str == 'TRACE':
        log_level = logging.DEBUG
    else:
        raise launch.util.LauncherError('InvalidOption', '{} is not a valid log level'.format(log_level_str))
    logging.basicConfig(format=LOGGING_FORMAT, level=log_level)
    if log_level_str in ('TRACE', 'CRITICAL'):
        return
    # now dampen the loud loggers
    for module in ['botocore', 'boto3']:
        logging.getLogger(module).setLevel(log_level + 10)


def do_main(args):
    _handle_logging(args['--log-level'].upper())

    config_path = args['--config-path']
    if args['create']:
        config = launch.config.get_validated_config(config_path)
        info_path = args['--info-path']
        if os.path.exists(info_path):
            raise launch.util.LauncherError('InputConflict', 'Target info path already exists!')
        write_json(info_path, launch.get_launcher(config).create(config))
        return 0

    info = load_json(args['--info-path'])
    launcher = launch.get_launcher(info)

    if args['wait']:
        launcher.wait(info)
        print('Cluster is ready!')
        return 0

    if args['describe']:
        print(json_prettyprint(launcher.describe(info)))
        return 0

    if args['pytest']:
        test_cmd = 'py.test'
        if args['--env'] is not None:
            if '=' in args['--env']:
                # User is attempting to do an assigment with the option
                raise launch.util.LauncherError(
                    'OptionError', "The '--env' option can only pass through environment variables "
                    "from the current environment. Set variables according to the shell being used.")
            var_list = args['--env'].split(',')
            launch.util.check_keys(os.environ, var_list)
            test_cmd = ' '.join(['{}={}'.format(e, os.environ[e]) for e in var_list]) + ' ' + test_cmd
        if len(args['<pytest_extras>']) > 0:
            test_cmd += ' ' + ' '.join(args['<pytest_extras>'])
        launcher.test(info, test_cmd)
        return 0

    if args['delete']:
        launcher.delete(info)
        return 0


def main(argv=None):
    args = docopt(__doc__, argv=argv, version='DC/OS Launch v.0.1')

    try:
        return do_main(args)
    except launch.util.LauncherError as ex:
        print('DC/OS Launch encountered an error!')
        print(repr(ex))
        return 1


if __name__ == '__main__':
    sys.exit(main())
