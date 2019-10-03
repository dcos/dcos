"""Panda package management for Windows

Usage:
  winpanda setup [options]

Options:
    --root-dir=<path>                DC/OS installation root directory.
                                     [default: {default_root_dpath}]
    --config-dir=<path>              DC/OS configuration directory.
                                     [default: {default_config_dpath}]
    --state-dir=<path>               DC/OS packages state directory.
                                     [default: {default_state_dpath}]
    --repository-dir=<path>          DC/OS local package repository directory.
                                     [default: {default_repository_dpath}]
    --master-private-ipaddr=<ipaddr> master node's local private IP-address.
                                     [default: 0.0.0.0]
    --local-private-ipaddr=<ipaddr>  agent node's local private IP-address.
                                     [default: 0.0.0.0]
    --distribution-storage-url=<url> DC/OS distribution storage URL.
                                     [default: {default_dstor_url}]
    --distribution-storage-pkgrepo=<path> DC/OS distribution storage URL.
                                     [default: {default_dstor_pkgrepo_path}]
"""
import sys

from docopt import docopt

# import actions
import constants as const
from core import command


class InstallationManager:
    """"""
    def __init__(self):
        """"""
        self.cli_args = self._get_cli_args()
        self.command_ = self._get_command()

    @staticmethod
    def _get_cli_args():
        """"""
        cli_argspec = __doc__.format(
            default_root_dpath=const.DCOS_INST_ROOT_DPATH_DFT,
            default_config_dpath=const.DCOS_CFG_ROOT_DPATH_DFT,
            default_state_dpath=const.DCOS_STATE_ROOT_DPATH_DFT,
            default_repository_dpath=const.DCOS_PKGREPO_ROOT_DPATH_DFT,
            default_dstor_url=const.DCOS_DSTOR_URL_DFT,
            default_dstor_pkgrepo_path=const.DCOS_DSTOR_PKGREPO_PATH_DFT
        )

        cli_args = docopt(cli_argspec)
        # print(f'cli_args: {cli_args}')

        return cli_args

    def _get_command(self):
        """"""
        command_name = None

        if self.cli_args['setup'] is True:
            command_name = 'setup'

        cmd_opts = {
            'inst_root_path': self.cli_args.get('--root-dir'),
            'inst_conf_path': self.cli_args.get('--config-dir'),
            'inst_pkgrepo_path': self.cli_args.get('--repository-dir'),
            'inst_state_path': self.cli_args.get('--state-dir'),
            'master-priv-ipaddr': self.cli_args.get('--master-private-ipaddr'),
            'local-priv-ipaddr': self.cli_args.get('--local-private-ipaddr'),
            'dstor_url': self.cli_args.get('--distribution-storage-url'),
            'dstor_pkgrepo_path': self.cli_args.get(
                '--distribution-storage-pkgrepo'
            )
        }

        return command.create(command_name=command_name, **cmd_opts)
        # The 'unsupported command' case is handled by the docopts module.


def main():
    """"""
    try:
        InstallationManager().command_.execute()
    except Exception as e:
        print('{}: {}'.format(type(e).__name__, e), file=sys.stderr)
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    sys.exit(main())
