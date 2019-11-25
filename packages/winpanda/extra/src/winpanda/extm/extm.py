"""Panda package management for Windows.

DC/OS package extra installation options manager definition.
"""
from common import logger
from common import exceptions as cm_exc
from common import utils as cm_utl
from extm import exceptions as extm_exc
import shlex


LOG = logger.get_logger(__name__)


class EXTCFG_SECTION:
    """Package installation extras configuration file section namess."""
    INSTALL = 'install'
    UNINSTALL = 'uninstall'


class EXTCFG_OPTION:
    """Package installation extras configuration file option names."""
    EXEC_EXT_CMD = 'exec_external_commands'


class PkgInstExtrasManager:
    """DC/OS package extra installation options manager."""
    def __init__(self, ext_conf):
        """Constructor.

        :param ext_conf: dict, package installation extras config
        """
        if not isinstance(ext_conf, dict):
            raise extm_exc.InstExtrasManagerConfigError(
                f'Invalid configuration container structure: {ext_conf}'
            )

        self.ext_conf = ext_conf

    def handle_install_extras(self):
        """DC/OS package install extra options handler."""
        msg_src = self.__class__.__name__
        LOG.debug(f'{msg_src}: Config: {self.ext_conf}')

        install_sect = self.ext_conf.get(EXTCFG_SECTION.INSTALL, {})
        LOG.debug(f'{msg_src}: Config: {EXTCFG_SECTION.INSTALL}:'
                  f' {install_sect}')

        if not isinstance(install_sect, dict):
            raise extm_exc.InstExtrasManagerConfigError(
                f'Invalid configuration container structure:'
                f' {EXTCFG_SECTION.INSTALL}: {install_sect}'
            )
        exec_ext_cmd_opt = install_sect.get(EXTCFG_OPTION.EXEC_EXT_CMD, [])
        LOG.debug(f'{msg_src}: Config: {EXTCFG_SECTION.INSTALL}:'
                  f' {EXTCFG_OPTION.EXEC_EXT_CMD}: {exec_ext_cmd_opt}')

        if not isinstance(exec_ext_cmd_opt, list):
            raise extm_exc.InstExtrasManagerConfigError(
                f'Invalid configuration container structure:'
                f' {EXTCFG_OPTION.EXEC_EXT_CMD}: {exec_ext_cmd_opt}'
            )

        # Handle the 'execute external commands' option
        self._exec_external_commands(*exec_ext_cmd_opt)

    def handle_uninstall_extras(self):
        """DC/OS package uninstall extra options handler."""
        msg_src = self.__class__.__name__
        uninstall_sect = self.ext_conf.get(EXTCFG_SECTION.UNINSTALL, {})

        if not isinstance(uninstall_sect, dict):
            raise extm_exc.InstExtrasManagerConfigError(
                f'Invalid configuration container structure:'
                f' {EXTCFG_SECTION.UNINSTALL}: {uninstall_sect}'
            )

        exec_ext_cmd_opt = uninstall_sect.get(EXTCFG_OPTION.EXEC_EXT_CMD, [])

        if not isinstance(exec_ext_cmd_opt, list):
            raise extm_exc.InstExtrasManagerConfigError(
                f'Invalid configuration container structure:'
                f' {EXTCFG_OPTION.EXEC_EXT_CMD}: {exec_ext_cmd_opt}'
            )

        # Handle the 'execute external commands' option
        self._exec_external_commands(*exec_ext_cmd_opt)

    def _exec_external_commands(self, *cmd_cl_defs):
        """Execute a chain of external commands.

        :param cmd_cl_defs: tuple(str), set of command line definitions
        """
        msg_src = self.__class__.__name__

        for cmd_cl_def in cmd_cl_defs:
            try:
                cl_elements = shlex.quote(cmd_cl_def)
                cm_utl.run_external_command(cl_elements)
                LOG.debug(f'{msg_src}: External command: {cl_elements}: OK')
            except cm_exc.ExternalCommandError as e:
                raise extm_exc.InstExtrasManagerError(
                    f'{type(e).__name__}: {e}'
                ) from e
