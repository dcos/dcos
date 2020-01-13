"""Panda package management for Windows.

DC/OS package extra installation options manager definition.
"""
import subprocess

from common import logger
from common import exceptions as cm_exc
from common import utils as cm_utl
from core.package.manifest import PackageManifest
from extm import exceptions as extm_exc


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
    def __init__(self, pkg_manifest):
        """Constructor.

        :param pkg_manifest: PackageManifest, DC/OS package manifest object
        """
        self._msg_src_base = self.__class__.__name__

        assert isinstance(pkg_manifest, PackageManifest), (
            f'{self._msg_src_base}: Argument: pkg_manifest:'
            f' Got {type(pkg_manifest).__name__} instead of PackageManifest'
        )
        self._pkg_manifest = pkg_manifest
        self._pkg_id = self._pkg_manifest.pkg_id
        self._ext_conf = self._pkg_manifest.pkg_extcfg

        self.msg_src = f'{self._msg_src_base}: {self._pkg_id.pkg_id}'

    def __str__(self):
        return str({
            'ext_conf': self._ext_conf,
        })

    def handle_install_extras(self):
        """DC/OS package install extra options handler."""
        install_sect = self._ext_conf.get(EXTCFG_SECTION.INSTALL, {})

        if not isinstance(install_sect, dict):
            raise extm_exc.InstExtrasManagerConfigError(
                f'Invalid configuration container structure:'
                f' {EXTCFG_SECTION.INSTALL}: {install_sect}'
            )
        exec_ext_cmd_opt = install_sect.get(EXTCFG_OPTION.EXEC_EXT_CMD, [])

        if not isinstance(exec_ext_cmd_opt, list):
            raise extm_exc.InstExtrasManagerConfigError(
                f'Invalid configuration container structure:'
                f' {EXTCFG_OPTION.EXEC_EXT_CMD}: {exec_ext_cmd_opt}'
            )

        # Handle the 'execute external commands' option
        self._exec_external_commands(*exec_ext_cmd_opt)

    def handle_uninstall_extras(self):
        """DC/OS package uninstall extra options handler."""
        uninstall_sect = self._ext_conf.get(EXTCFG_SECTION.UNINSTALL, {})

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
        for cmd_id, cmd_cl_def in enumerate(cmd_cl_defs, start=1):
            try:
                cmd_run_result = cm_utl.run_external_command(cmd_cl_def)
                LOG.debug(
                    f'{self.msg_src}: Run external command (cmd_id={cmd_id}):'
                    f' {cmd_cl_def}: OK')
                self._save_extcmd_output(str(cmd_id), cmd_run_result)
            except cm_exc.ExternalCommandError as e:
                LOG.debug(
                    f'{self.msg_src}: Run external command (cmd_id={cmd_id}):'
                    f' {cmd_cl_def}: {type(e).__name__}: {e}')
                self._save_extcmd_output(str(cmd_id), e)
                raise extm_exc.InstExtrasManagerError(
                    f'{type(e).__name__}: {e}'
                ) from e

    def _save_extcmd_output(self, cmd_id, cmd_run_result):
        """Save external command's return code and content of its standard
        output and error streams.

        :param cmd_id:         str, command ID
        :param cmd_run_result: subprocess.CompletedProcess|
                               subprocess.SubprocessError, command execution
                               result descriptor object
        """
        failure_descriptor = getattr(cmd_run_result, '__cause__', None)

        if failure_descriptor:
            cmd_spec = getattr(failure_descriptor, 'cmd', None)
            cmd_retcode = getattr(failure_descriptor, 'returncode', None)
            cmd_stdout = getattr(failure_descriptor, 'stdout', None)
            cmd_stderr = getattr(failure_descriptor, 'stderr', None)
        else:
            cmd_spec = getattr(cmd_run_result, 'args', None)
            cmd_retcode = getattr(cmd_run_result, 'returncode', None)
            cmd_stdout = getattr(cmd_run_result, 'stdout', None)
            cmd_stderr = getattr(cmd_run_result, 'stderr', None)

        LOG.debug(
            f'{self.msg_src}: Run external command (cmd_id={cmd_id}):'
            f' {cmd_spec}: return code: {cmd_retcode}'
        )
        LOG.debug(
            f'{self.msg_src}: Run external command (cmd_id={cmd_id}):'
            f' {cmd_spec}: stdout: {cmd_stdout}'
        )
        LOG.debug(
            f'{self.msg_src}: Run external command (cmd_id={cmd_id}):'
            f' {cmd_spec}: stderr: {cmd_stderr}'
        )
