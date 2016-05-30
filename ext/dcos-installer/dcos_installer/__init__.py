import argparse
import logging
import os
import sys

from dcos_installer import backend
from dcos_installer.cli import dispatch_action
from dcos_installer.action_lib.prettyprint import print_header
from dcos_installer import async_server
from dcos_installer.util import GENCONF_DIR

import coloredlogs

log = logging.getLogger(__name__)

LOG_FORMAT = '%(asctime)-15s %(module)s %(message)s'


def make_default_dir(dir=GENCONF_DIR):
    """
    So users do not have to set the directories in the config.yaml,
    we build them using sane defaults here first.
    """
    if not os.path.exists(dir):
        log.info('Creating {}'.format(dir))
        os.makedirs(dir)


def log_warn_only():
    """Drop to warning level and down to get around gen.generate() log.info
    output"""
    coloredlogs.install(
        level='WARNING',
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


def print_validation_errors(messages):
    log.error("Validation of configuration parameters failed: ")
    for key, message in messages.items():
        log.error('{}: {}'.format(key, message))


def validate_ssh_config_or_exit():
    validation_errors = backend.do_validate_ssh_config()
    if validation_errors:
        print_validation_errors(validation_errors)
        sys.exit(1)


class DcosInstaller:
    def __init__(self, args=None):
        """
        The web based installer leverages Flask to present end-users of
        dcos_installer with a clean web interface to configure their
        site-based installation of DC/OS.
        """
        # If no args are passed to the class, then we're calling this
        # class from another library or code so we shouldn't execute
        # parser or anything else
        if args:
            options = self.parse_args(args)
            if len(options.hash_password) > 0:
                print_header("HASHING PASSWORD TO SHA512")
                backend.hash_password(options.hash_password)
                sys.exit(0)

            make_default_dir()

            if options.web:
                print_header("Starting DC/OS installer in web mode")
                async_server.start(options)

            if options.validate_config:
                print_header('VALIDATING CONFIGURATION')
                log_warn_only()
                validation_errors = backend.do_validate_gen_config()
                if validation_errors:
                    print_validation_errors(validation_errors)
                    sys.exit(1)
                sys.exit(0)

            if options.genconf:
                print_header("EXECUTING CONFIGURATION GENERATION")
                code = backend.do_configure()
                if code != 0:
                    sys.exit(1)
                sys.exit(0)

            validate_ssh_config_or_exit()

            dispatch_action(options)

    def parse_args(self, args):
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
            '--disable-analytics',
            action='store_true',
            default=False,
            help="Disable sending installer analytics data to SegementIO")

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
        return options
