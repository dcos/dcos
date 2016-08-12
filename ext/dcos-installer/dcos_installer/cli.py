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


def start_installer(args):
    """
    The web based installer leverages Flask to present end-users of
    dcos_installer with a clean web interface to configure their
    site-based installation of DC/OS.
    """
    # If no args are passed to the class, then we're calling this
    # class from another library or code so we shouldn't execute
    # parser or anything else
    options = parse_args(args)
    setup_logger(options)
    dcos_installer.cli_dispatcher.dispatch(options)


def parse_args(args):
    def print_usage():
        return """
Install Mesosophere's Data Center Operating System

dcos_installer [-h] [-f LOG_FILE] [--hash-password HASH_PASSWORD] [-v] [--web |
                                                                        --genconf |
                                                                        --aws-cloudformation [--upload-s3] |
                                                                        --preflight |
                                                                        --deploy |
                                                                        --postflight |
                                                                        --uninstall |
                                                                        --validate-config |
                                                                        --version]

Environment Settings:

PORT                  Set the :port to run the web UI
CHANNEL_NAME          ADVANCED - Set build channel name
BOOTSTRAP_ID          ADVANCED - Set bootstrap ID for build

"""

    """
    Parse CLI arguments and return a map of options.
    """
    parser = argparse.ArgumentParser(usage=print_usage())
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

    def add_mode(name, help):
        mutual_exc.add_argument(
            '--{}'.format(name),
            action='store_const',
            const=name,
            dest='action')

    # Add all arg modes
    for name, value in dcos_installer.cli_dispatcher.dispatch_dict_simple.items():
        add_mode(name, value[1])

    for name, value in dcos_installer.cli_dispatcher.dispatch_dict_aio.items():
        add_mode(name, value[1])

    options = parser.parse_args(args)
    return options


def main():
    if len(sys.argv) == 1:
        start_installer(["--genconf"])
    else:
        start_installer(sys.argv[1:])

if __name__ == '__main__':
    main()
