import argparse
import coloredlogs
import logging
import sys

import dcos_installer.cli_dispatcher


log = logging.getLogger(__name__)


def setup_logger(options):
    level = 'INFO'
    if options.verbose:
        level = 'DEBUG'
    coloredlogs.install(
        level=level,
        level_styles={
            'warn': {
                'color': 'yellow'
            },
            'error': {
                'color': 'red',
                'bold': True,
            },
        },
        fmt='%(message)s',
        isatty=True
    )
    log.debug("Logger set to DEBUG")


def parse_args(args):
    """
    Parse CLI arguments and return a map of options.
    """
    parser = argparse.ArgumentParser(
        description="DC/OS Install and Configuration Utility")
    mutual_exc = parser.add_mutually_exclusive_group()

    mutual_exc.add_argument(
        '--hash-password',
        default='',
        type=str,
        help='Hash a password on the CLI for use in the config.yaml.'
    )

    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Verbose log output (DEBUG).')

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=9000,
        help=argparse.SUPPRESS)

    parser.add_argument(
        '--offline',
        action='store_true',
        help='Do not install preflight prerequisites on CentOS7, RHEL7 in web mode'
    )

    parser.add_argument(
        '--cli-telemetry-disabled',
        action='store_true',
        help='Disable the CLI telemetry gathering for SegmentIO')

    def add_mode(name, help_msg):
        mutual_exc.add_argument(
            '--{}'.format(name),
            action='store_const',
            const=name,
            dest='action',
            help=help_msg)

    # Add all arg modes
    for name, value in dcos_installer.cli_dispatcher.dispatch_dict_simple.items():
        add_mode(name, value[1])

    for name, value in dcos_installer.cli_dispatcher.dispatch_dict_aio.items():
        add_mode(name, value[1])

    return parser.parse_args(args)


def main():
    if len(sys.argv) == 1:
        args = ["--genconf"]
    else:
        args = sys.argv[1:]

    options = parse_args(args)
    setup_logger(options)
    dcos_installer.cli_dispatcher.dispatch(options)


if __name__ == '__main__':
    main()
