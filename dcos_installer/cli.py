import argparse
import json
import logging
import os
import sys

import coloredlogs
from passlib.hash import sha512_crypt

import dcos_installer.config
import dcos_installer.constants
import gen.calc
from dcos_installer import backend
from dcos_installer.prettyprint import print_header

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


def do_version(args):
    print(json.dumps(
        {
            'version': gen.calc.entry['must']['dcos_version'],
            'variant': os.environ['BOOTSTRAP_VARIANT']},
        indent=2, sort_keys=True))
    return 0


def web_installer(options):
    log.error('The DC/OS web installer (--web) has been removed.\n'
              'Please refer to the DC/OS Installation guide at https://docs.mesosphere.com/1.12/installing/')
    sys.exit(1)


dispatch_dict_simple = {
    'version': (do_version, None, 'Print the DC/OS version'),
    'web': (
        web_installer,
        'Starting DC/OS installer in web mode',
        'Run the web interface'),
    'genconf': (
        lambda args: backend.do_configure(),
        'EXECUTING CONFIGURATION GENERATION',
        'Create DC/OS install files customized according to {}.'.format(dcos_installer.constants.CONFIG_PATH)),
    'aws-cloudformation': (
        lambda args: backend.do_aws_cf_configure(),
        'EXECUTING AWS CLOUD FORMATION TEMPLATE GENERATION',
        'Generate AWS Advanced AWS CloudFormation templates using the provided config')
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
