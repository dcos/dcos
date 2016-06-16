import asyncio
import coloredlogs
import logging
import os
import sys

from dcos_installer import async_server, action_lib, backend
from dcos_installer.action_lib.prettyprint import print_header, PrettyPrint
from dcos_installer.installer_analytics import InstallerAnalytics

from ssh.utils import AbstractSSHLibDelegate

log = logging.getLogger(__name__)
installer_analytics = InstallerAnalytics()


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
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

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


def dispatch_option(args):
    """Dispatches ClI options which are not installer actions"""
    def web(args):
        print_header("Starting DC/OS installer in web mode")
        async_server.start(args)

    def hash_password(args):
        if len(args.hash_password) > 0:
            print_header("HASHING PASSWORD TO SHA512")
            backend.hash_password(args.hash_password)
            return 0

    def validate_config(args):
        print_header('VALIDATING CONFIGURATION')
        log_warn_only()
        validation_errors = backend.do_validate_gen_config()
        if validation_errors:
            print_validation_errors(validation_errors)
            return 1
        return 0

    def genconf(args):
        print_header("EXECUTING CONFIGURATION GENERATION")
        code = backend.do_configure()
        if code != 0:
            return 1
        return 0

    def version(args):
        print("DC/OS Bootstrap ID: " + os.environ["BOOTSTRAP_ID"])

    for action in ['web', 'hash_password', 'validate_config', 'version', 'genconf']:
        if getattr(args, action):
            sys.exit(locals()[action](args))


def dispatch_action(args):
    """Dispatches CLI options which are installer actions ran through
    AIO loop construct"""
    validate_ssh_config_or_exit()

    def preflight(args):
        print_header("EXECUTING PREFLIGHT")
        return action_lib.run_preflight

    def postflight(args):
        print_header("EXECUTING POSTFLIGHT")
        return action_lib.run_postflight

    def deploy(args):
        print_header("EXECUTING DC/OS INSTALLATION")
        return action_lib.install_dcos

    def uninstall(args):
        print_header("EXECUTING UNINSTALL")
        tall_enough_to_ride()
        return action_lib.uninstall_dcos

    def install_prereqs(args):
        print_header("EXECUTING INSTALL PREREQUISITES")
        return action_lib.install_prereqs

    for action in ['deploy', 'preflight', 'postflight', 'uninstall', 'install_prereqs']:
        if getattr(args, action):
            errors = run_loop(locals()[action](args), args)
            installer_analytics.send(
                action="installer_{}".format(action),
                install_method="cli",
                num_errors=errors,
            )
            exit_code = 1 if errors > 0 else 0
            sys.exit(exit_code)
