"""Panda package management for Windows.

CLI entry point definition.
"""
from pathlib import Path
import traceback
import sys

from docopt import docopt, DocoptExit

sys.path.insert(1, f'{Path(sys.path[0]).parent}')

from common import constants as cm_const
from common.cli import (
    CLI_ARGSPEC, CLI_COMMAND, CLI_CMDTARGET, VALID_CLI_CMDTARGETS, CLI_CMDOPT
)
from common import storage
from common import logger
from common.logger import LOG_LEVEL
from core import command


LOG = logger.get_logger(__name__)


class DCOSInstallationManager:
    """DC/OS installation manager."""
    def __init__(self):
        """Constructor."""
        self.cli_args = self._get_cli_args()
        self.command_ = self._get_command()

    @staticmethod
    def _get_cli_args():
        """Retrieve set of CLI arguments."""
        cli_argspec = CLI_ARGSPEC.format(
            cmd_setup=CLI_COMMAND.SETUP,
            cmd_upgrade=CLI_COMMAND.UPGRADE,
            cmd_start=CLI_COMMAND.START,
            valid_cmd_targets=', '.join(VALID_CLI_CMDTARGETS),
            default_cmd_target=CLI_CMDTARGET.PKGALL,
            default_root_dpath=storage.DCOS_INST_ROOT_DPATH_DFT,
            default_config_dpath=storage.DCOS_INST_CFG_DPATH_DFT,
            default_state_dpath=storage.DCOS_INST_STATE_DPATH_DFT,
            default_repository_dpath=storage.DCOS_INST_PKGREPO_DPATH_DFT,
            default_var_dpath=storage.DCOS_INST_VAR_DPATH_DFT,
            default_clustercfg_fpath=cm_const.DCOS_CLUSTER_CFG_FNAME_DFT
        )

        cli_args = docopt(cli_argspec)

        # Verify actual command target value
        cmdtarget = cli_args.get('--target')
        if cmdtarget not in VALID_CLI_CMDTARGETS:
            LOG.critical(f'CLI: Invalid option value: --target: {cmdtarget}')
            raise DocoptExit()

        LOG.debug(f'cli_args: {cli_args}')

        return cli_args

    def _get_command(self):
        """Discover the command name and create an instance of appropriate
        command manager object.
        """
        # Discover actual command name
        command_name = None

        if self.cli_args[CLI_COMMAND.SETUP] is True:
            command_name = CLI_COMMAND.SETUP
        elif self.cli_args[CLI_COMMAND.UPGRADE] is True:
            command_name = CLI_COMMAND.UPGRADE
        elif self.cli_args[CLI_COMMAND.START] is True:
            command_name = CLI_COMMAND.START

        cmd_opts = {
            CLI_CMDOPT.CMD_NAME: command_name,
            CLI_CMDOPT.CMD_TARGET: self.cli_args.get('--target'),
            CLI_CMDOPT.INST_ROOT: self.cli_args.get('--inst-root-dir'),
            CLI_CMDOPT.INST_CONF: self.cli_args.get('--inst-config-dir'),
            CLI_CMDOPT.INST_STATE: self.cli_args.get('--inst-state-dir'),
            CLI_CMDOPT.INST_PKGREPO: self.cli_args.get('--inst-repo-dir'),
            CLI_CMDOPT.INST_VAR: self.cli_args.get('--inst-var-data-dir'),
            CLI_CMDOPT.INST_CLEAN: self.cli_args.get('--clean'),
            CLI_CMDOPT.MASTER_PRIVIPADDR: self.cli_args.get(
                '--master-priv-ipaddr'
            ),
            CLI_CMDOPT.LOCAL_PRIVIPADDR: self.cli_args.get(
                '--local-priv-ipaddr'
            ),
            CLI_CMDOPT.DSTOR_URL: self.cli_args.get('--dstor-url'),
            CLI_CMDOPT.DSTOR_PKGREPOPATH: self.cli_args.get('--dstor-pkgrepo'),
            CLI_CMDOPT.DSTOR_PKGLISTPATH: self.cli_args.get('--dstor-pkglist'),
            CLI_CMDOPT.DSTOR_DCOSCFGPATH: self.cli_args.get('--dstor-dcoscfg'),
            CLI_CMDOPT.DCOS_CLUSTERCFGPATH: self.cli_args.get(
                '--cluster-cfgfile'
            )
        }

        return command.create(**cmd_opts)
        # The 'unsupported command' case is handled by the docopts module.


def main():
    """"""
    log_level = LOG_LEVEL.DEBUG
    log_fpath = Path('C:\\d2iq\\dcos\\var\\log\\winpanda',
                     cm_const.APP_LOG_FNAME)
    try:
        log_fpath.parent.mkdir(parents=True, exist_ok=True)
    except (OSError, RuntimeError):
        log_fpath = Path('.', cm_const.APP_LOG_FNAME)
    logger.master_setup(
        log_level=log_level, file_path=log_fpath,
        file_size=cm_const.APP_LOG_FSIZE_MAX,
        history_size=cm_const.APP_LOG_HSIZE_MAX
    )
    try:
        DCOSInstallationManager().command_.execute()
    except Exception as e:
        if log_level == LOG_LEVEL.DEBUG:
            LOG.critical(f'\n{"".join(traceback.format_exc())}')
            traceback.print_exc()
        else:
            LOG.critical(f'{type(e).__name__}: {e}')
            print(f'{type(e).__name__}: {e}', file=sys.stderr)

        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
