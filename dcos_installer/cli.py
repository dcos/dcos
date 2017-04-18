import argparse
import asyncio
import json
import logging
import os
import sys

import coloredlogs
from passlib.hash import sha512_crypt

import dcos_installer.async_server
import dcos_installer.config
import dcos_installer.constants
import gen.calc
from dcos_installer import action_lib, backend
from dcos_installer.config import Config
from dcos_installer.installer_analytics import InstallerAnalytics
from dcos_installer.prettyprint import PrettyPrint, print_header

from ssh.utils import AbstractSSHLibDelegate

log = logging.getLogger(__name__)
installer_analytics = InstallerAnalytics()


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


class CliDelegate(AbstractSSHLibDelegate):
    def on_update(self, future, callback_called):
        chain_name, result_object, host = future.result()
        callback_called.set_result(True)
        log.debug('on_update executed for {}'.format(chain_name))

    def on_done(self, name, result, host_status=None):
        print_header('STAGE {}'.format(name))

    def prepare_status(self, name, nodes):
        pass


def run_loop(action, options):
    assert callable(action)
    loop = asyncio.get_event_loop()

    print_header('START {}'.format(action.__name__))
    try:
        config = dcos_installer.config.Config(dcos_installer.constants.CONFIG_PATH)
        cli_delegate = CliDelegate()
        result = loop.run_until_complete(action(config, block=True, async_delegate=cli_delegate, options=options))
        pp = PrettyPrint(result)
        pp.stage_name = action.__name__
        pp.beautify('print_data')

    finally:
        loop.close()
    exitcode = 0
    for host_result in result:
        for command_result in host_result:
            for host, process_result in command_result.items():
                if process_result['returncode'] != 0:
                    exitcode += 1
    print_header('ACTION {} COMPLETE'.format(action.__name__))
    pp.print_summary()
    return exitcode


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


def do_version(args):
    print(json.dumps(
        {
            'version': gen.calc.entry['must']['dcos_version'],
            'variant': os.environ['BOOTSTRAP_VARIANT']},
        indent=2, sort_keys=True))
    return 0


def do_validate_config(args):
    log_warn_only()
    config = Config(dcos_installer.constants.CONFIG_PATH)
    validation_errors = config.do_validate(include_ssh=True)
    if validation_errors:
        print_validation_errors(validation_errors)
        return 1
    return 0


dispatch_dict_simple = {
    'version': (do_version, None, 'Print the DC/OS version'),
    'web': (
        dcos_installer.async_server.start,
        'Starting DC/OS installer in web mode',
        'Run the web interface'),
    'genconf': (
        lambda args: backend.do_configure(),
        'EXECUTING CONFIGURATION GENERATION',
        'Create DC/OS install files customized according to {}.'.format(dcos_installer.constants.CONFIG_PATH)),
    'validate-config': (
        do_validate_config,
        'VALIDATING CONFIGURATION',
        'Validate the configuration for executing --genconf and deploy arguments in config.yaml'),
    'aws-cloudformation': (
        lambda args: backend.do_aws_cf_configure(),
        'EXECUTING AWS CLOUD FORMATION TEMPLATE GENERATION',
        'Generate AWS Advanced AWS CloudFormation templates using the provided config')
}

dispatch_dict_aio = {
    'preflight': (
        action_lib.run_preflight,
        'EXECUTING_PREFLIGHT',
        'Execute the preflight checks on a series of nodes.'),
    'install-prereqs': (
        action_lib.install_prereqs,
        'EXECUTING INSTALL PREREQUISITES',
        'Install the cluster prerequisites.'),
    'deploy': (
        action_lib.install_dcos,
        'EXECUTING DC/OS INSTALLATION',
        'Execute a deploy.'),
    'postflight': (
        action_lib.run_postflight,
        'EXECUTING POSTFLIGHT',
        'Execute postflight checks on a series of nodes.')
}


# TODO(cmaloney): This should only be in enterprise / isn't useful in open currently.
def do_hash_password(password):
    if password is None:
        password = ''
        while True:
            password = input('Password: ')
            if password:
                break
            else:
                log.error('Must provide a non-empty password')

    print_header("HASHING PASSWORD TO SHA512")
    hashed_password = sha512_crypt.encrypt(password)
    return hashed_password


def dispatch(args):
    """ Dispatches the selected mode based on command line args. """
    if args.action == 'set-superuser-password':
        password_hash = do_hash_password(args.password)
        messages = backend.create_config_from_post(
            {'superuser_password_hash': password_hash},
            dcos_installer.constants.CONFIG_PATH)
        if messages:
            log.error("Unable to save password: {}".format(messages))
            sys.exit(1)
        sys.exit(0)

    if args.action == 'hash-password':
        # TODO(cmaloney): Import a function from the auth stuff to do the hashing and guarantee it
        # always matches
        byte_str = do_hash_password(args.password).encode('ascii')
        sys.stdout.buffer.write(byte_str + b'\n')
        sys.exit(0)

    if args.action == 'generate-node-upgrade-script':
        status = backend.generate_node_upgrade_script(args.installed_cluster_version)
        sys.exit(status)

    if args.action in dispatch_dict_simple:
        action = dispatch_dict_simple[args.action]
        if action[1] is not None:
            print_header(action[1])
        sys.exit(action[0](args))

    # Dispatches CLI options which are installer actions ran through AIO event loop
    if args.action in dispatch_dict_aio:
        action = dispatch_dict_aio[args.action]
        if do_validate_config(args) != 0:
            sys.exit(1)
        if action[1] is not None:
            print_header(action[1])
        errors = run_loop(action[0], args)
        if not args.cli_telemetry_disabled:
            installer_analytics.send(
                action=args.action,
                install_method="cli",
                num_errors=errors,
            )
        sys.exit(1 if errors > 0 else 0)

    print("Internal Error: No known way to dispatch {}".format(args.action))
    sys.exit(1)


class ArgsAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        assert self.option_strings[0][:2] == '--'
        setattr(namespace, 'action', self.option_strings[0][2:])
        setattr(namespace, self.dest, values)


def get_argument_parser():
    """
    Parse CLI arguments and return a map of options.
    """
    parser = argparse.ArgumentParser(
        description="DC/OS Install and Configuration Utility")
    mutual_exc = parser.add_mutually_exclusive_group()

    mutual_exc.add_argument(
        '--hash-password',
        action=ArgsAction,
        dest='password',
        metavar='password',
        nargs='?',
        help='Hash a password and print the results to copy into a config.yaml.'
    )

    mutual_exc.add_argument(
        '--set-superuser-password',
        action=ArgsAction,
        metavar='password',
        dest='password',
        nargs='?',
        help='Hash the given password and store it as the superuser password in config.yaml'
    )

    mutual_exc.add_argument(
        '--generate-node-upgrade-script',
        action=ArgsAction,
        metavar='installed_cluster_version',
        dest='installed_cluster_version',
        nargs='?',
        help='Generate a script that upgrades DC/OS nodes running installed_cluster_version'
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
    for name, value in dispatch_dict_simple.items():
        add_mode(name, value[2])

    for name, value in dispatch_dict_aio.items():
        add_mode(name, value[2])

    parser.set_defaults(action='genconf')

    return parser


def main():
    # Passd in by installer_internal_wrapper since in ash exec can't set argv0
    # directly to not be the name of the binary being executed.
    if 'INSTALLER_ARGV0' in os.environ:
        sys.argv[0] = os.environ['INSTALLER_ARGV0']
    argument_parser = get_argument_parser()

    try:
        options = argument_parser.parse_args()
        setup_logger(options)
        dispatch(options)
    except dcos_installer.config.NoConfigError as ex:
        print(ex)
        sys.exit(1)


if __name__ == '__main__':
    main()
