import argparse
import asyncio
import coloredlogs
import json
import logging
import os
import sys

from passlib.hash import sha512_crypt

import dcos_installer.async_server
import gen.calc
from dcos_installer import action_lib, backend
from dcos_installer.prettyprint import print_header, PrettyPrint
from dcos_installer.installer_analytics import InstallerAnalytics

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
        config = backend.get_config()
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


def tall_enough_to_ride():
    choices_true = ['yes', 'y']
    choices_false = ['no', 'n']
    while True:
        do_uninstall = input('This will uninstall DC/OS on your cluster. You may need to manually remove '
                             '/var/lib/zookeeper in some cases after this completes, please see our documentation '
                             'for details. Are you ABSOLUTELY sure you want to proceed? [ (y)es/(n)o ]: ')
        if do_uninstall.lower() in choices_true:
            return
        elif do_uninstall.lower() in choices_false:
            sys.exit(1)
        else:
            log.error('Choices are [y]es or [n]o. "{}" is not a choice'.format(do_uninstall))


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


def do_version(args):
    print(json.dumps(
        {
            'version': gen.calc.entry['must']['dcos_version'],
            'variant': os.environ['BOOTSTRAP_VARIANT']},
        indent=2, sort_keys=True))
    return 0


def do_validate_config(args):
    log_warn_only()
    validation_errors = backend.do_validate_gen_config()
    if validation_errors:
        print_validation_errors(validation_errors)
        return 1
    return 0


def do_uninstall(*args, **kwargs):
    tall_enough_to_ride()
    return action_lib.uninstall_dcos(*args, **kwargs)


dispatch_dict_simple = {
    'version': (do_version, None, 'Print the DC/OS version'),
    'web': (
        dcos_installer.async_server.start,
        'Starting DC/OS installer in web mode',
        'Run the web interface'),
    'genconf': (
        lambda args: backend.do_configure(),
        'EXECUTING CONFIGURATION GENERATION'
        'Execute the configuration generation (genconf).'),
    'validate-config': (
        do_validate_config,
        'VALIDATING CONFIGURATION',
        'Validate the configuration for executing --genconf and deploy arguments in config.yaml')
}

dispatch_dict_aio = {
    'preflight': (
        action_lib.run_preflight,
        'EXECUTING_PREFLIGHT',
        'Execute the preflight checks on a series of nodes.'),
    'install-prereqs': (
        action_lib.install_prereqs,
        'EXECUTING INSTALL PREREQUISITES',
        'Execute the preflight checks on a series of nodes.'),
    'deploy': (
        action_lib.install_dcos,
        'EXECUTING DC/OS INSTALLATION',
        'Execute a deploy.'),
    'postflight': (
        action_lib.run_postflight,
        'EXECUTING POSTFLIGHT',
        'Execute postflight checks on a series of nodes.'),
    'uninstall': (
        do_uninstall,
        'EXECUTING UNINSTALL',
        'Execute uninstall on target hosts.')
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
    if getattr(args, 'set_superuser_password'):
        assert len(args.set_superuser_password) == 1
        password_hash = do_hash_password(args.set_superuser_password[0])
        err, messages = backend.create_config_from_post({'superuser_password_hash': password_hash})
        if err:
            log.error("Unable to save password: {}".format(messages))
            sys.exit(1)
        sys.exit(0)

    if getattr(args, 'hash_password'):
        assert len(args.hash_password) == 1
        # TODO(cmaloney): Import a function from the auth stuff to do the hashing and guarantee it
        # always matches
        byte_str = do_hash_password(args.hash_password[0]).encode('ascii')
        sys.stdout.buffer.write(byte_str + b'\n')
        sys.exit(0)

    if args.action in dispatch_dict_simple:
        action = dispatch_dict_simple[args.action]
        if action[1] is not None:
            print_header(action[1])
        sys.exit(action[0](args))

    # Dispatches CLI options which are installer actions ran through AIO event loop
    if args.action in dispatch_dict_aio:
        action = dispatch_dict_aio[args.action]
        validate_ssh_config_or_exit()
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


def parse_args(args):
    """
    Parse CLI arguments and return a map of options.
    """
    parser = argparse.ArgumentParser(
        description="DC/OS Install and Configuration Utility")
    mutual_exc = parser.add_mutually_exclusive_group()

    mutual_exc.add_argument(
        '--hash-password',
        action='append',
        nargs='?',
        help='Hash a password and print the results to copy into a config.yaml.'
    )

    mutual_exc.add_argument(
        '--set-superuser-password',
        action='append',
        nargs='?',
        help='Hash the given password and store it as the superuser password in config.yaml'
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
        add_mode(name, value[1])

    for name, value in dispatch_dict_aio.items():
        add_mode(name, value[1])

    return parser.parse_args(args)


def main():
    if len(sys.argv) == 1:
        args = ["--genconf"]
    else:
        args = sys.argv[1:]

    options = parse_args(args)
    setup_logger(options)
    dispatch(options)

if __name__ == '__main__':
    main()
