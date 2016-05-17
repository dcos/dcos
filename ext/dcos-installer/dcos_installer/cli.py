import asyncio
import logging
import sys

from dcos_installer import action_lib, backend
from dcos_installer.util import CONFIG_PATH
from dcos_installer.installer_analytics import InstallerAnalytics
from dcos_installer.action_lib.prettyprint import print_header, PrettyPrint
from ssh.utils import AbstractSSHLibDelegate


log = logging.getLogger(__name__)


class CliDelegate(AbstractSSHLibDelegate):
    def on_update(self, future, callback_called):
        chain_name, result_object, host = future.result()
        callback_called.set_result(True)
        log.debug('on_update executed for {}'.format(chain_name))

    def on_done(self, name, result, host_status=None):
        print_header('STAGE {}'.format(name))


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


def get_new_analytics(config_path=CONFIG_PATH):
    return InstallerAnalytics(backend.get_config(config_path))


def dispatch_action(args):
    installer_analytics = get_new_analytics()

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
            if not args.disable_analytics:
                installer_analytics.send(
                    action=action,
                    install_method="cli",
                    num_errors=errors,
                )
            exit_code = 1 if errors > 0 else 0
            sys.exit(exit_code)
