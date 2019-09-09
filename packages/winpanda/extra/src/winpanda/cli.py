"""Panda package management for Windows

Usage:
  winpanda setup [options]

Options:
    --root-dir=<path>           DC/OS installation root directory.
                                [default: {default_root_dpath}]
    --config-dir=<path>         DC/OS configuration directory.
                                [default: {default_config_dpath}]
    --state-dir=<path>          DC/OS packages state directory.
                                [default: {default_state_dpath}]
    --repository-dir=<path>     DC/OS local package repository directory.
                                [default: {default_repository_dpath}]
"""
import sys

from docopt import docopt

import actions
import constants


def main():
    cli_argspec = __doc__.format(
        default_root_dpath=constants.DCOS_INSTALL_ROOT_DPATH_DFT,
        default_config_dpath=constants.DCOS_CFG_ROOT_DPATH_DFT,
        default_state_dpath=constants.DCOS_STATE_ROOT_DPATH_DFT,
        default_repository_dpath=constants.DCOS_REPO_ROOT_DPATH_DFT,
    )

    cli_args = docopt(cli_argspec)

    install = None     # TODO: Pending implementation.
    repository = None  # TODO: Pending implementation.

    try:
        if cli_args['setup'] is True:
            actions.setup(install, repository)
        # The 'unsupported command' case is handled by the docopts module.
    except Exception as e:
        print("{}: {}".format(type(e).__name__, e), file=sys.stderr)
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    sys.exit(main())

