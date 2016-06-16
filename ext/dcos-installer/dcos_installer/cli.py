import argparse
import coloredlogs
import logging
import sys

from dcos_installer.cli_dispatcher import dispatch_option, dispatch_action


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
    dispatch_option(options)
    dispatch_action(options)


def parse_args(args):
    def print_usage():
        return """
Install Mesosophere's Data Center Operating System

dcos_installer [-h] [-f LOG_FILE] [--hash-password HASH_PASSWORD] [-v]
[--web | --genconf | --preflight | --deploy | --postflight | --uninstall | --validate-config | --test]

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

    parser.add_argument(
        '--hash-password',
        default='',
        type=str,
        help='Hash a password on the CLI for use in the config.yaml.'
    )

    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        default=False,
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
        default=False,
        help='Do not install preflight prerequisites on CentOS7, RHEL7 in web mode'
    )

    mutual_exc.add_argument(
        '--web',
        action='store_true',
        default=False,
        help='Run the web interface.')

    mutual_exc.add_argument(
        '--genconf',
        action='store_true',
        default=False,
        help='Execute the configuration generation (genconf).')

    mutual_exc.add_argument(
        '--preflight',
        action='store_true',
        default=False,
        help='Execute the preflight checks on a series of nodes.')

    mutual_exc.add_argument(
        '--install-prereqs',
        action='store_true',
        default=False,
        help='Install preflight prerequisites. Works only on CentOS7 and RHEL7.')

    mutual_exc.add_argument(
        '--deploy',
        action='store_true',
        default=False,
        help='Execute a deploy.')

    mutual_exc.add_argument(
        '--postflight',
        action='store_true',
        default=False,
        help='Execute postflight checks on a series of nodes.')

    mutual_exc.add_argument(
        '--uninstall',
        action='store_true',
        default=False,
        help='Execute uninstall on target hosts.')

    mutual_exc.add_argument(
        '--validate-config',
        action='store_true',
        default=False,
        help='Validate the configuration for executing --genconf and deploy arguments in config.yaml')

    mutual_exc.add_argument(
        '--test',
        action='store_true',
        default=False,
        help='Performs tests on the dcos_installer application')

    options = parser.parse_args(args)
    return options


def main():
    if len(sys.argv) == 1:
        start_installer(["--genconf"])
    else:
        start_installer(sys.argv[1:])

if __name__ == '__main__':
    main()
