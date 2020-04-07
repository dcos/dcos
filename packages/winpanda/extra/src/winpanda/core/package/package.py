"""Panda package management for Windows.

DC/OS package controller and helper type definitions.
"""
from pathlib import Path

from .manifest import PackageManifest
from .id import PackageId
from cfgm import exceptions as cfgm_exc
from cfgm.cfgm import PkgConfManager
from common import logger
from common import utils as cm_utl
from common.storage import ISTOR_NODE, IStorNodes
from core import exceptions as cr_exc
from extm.extm import PkgInstExtrasManager
from svcm import exceptions as svcm_exc
from svcm.nssm import SVC_STATUS, WinSvcManagerNSSM


LOG = logger.get_logger(__name__)


class Package:
    """Package manager."""
    def __init__(self, pkg_id: PackageId = None, istor_nodes: IStorNodes = None,
                 cluster_conf: dict = None, extra_context: dict = None,
                 manifest: PackageManifest = None):
        """Constructor.

        :param pkg_id:        PackageId, package ID
        :param istor_nodes:   IStorNodes, DC/OS installation storage nodes (set
                              of pathlib.Path objects)
        :param cluster_conf:  dict, configparser.ConfigParser.read_dict()
                              compatible data. DC/OS cluster setup parameters
        :param extra_context: dict, extra 'key=value' data to be added to the
                              resource rendering context
        :param manifest:      PackageManifest, DC/OS package manifest object
        """
        self.msg_src = self.__class__.__name__

        if manifest is None:
            manifest = PackageManifest(
                pkg_id=pkg_id, istor_nodes=istor_nodes,
                cluster_conf=cluster_conf, extra_context=extra_context
            )
        self.manifest = manifest

        self.cfg_manager = PkgConfManager(pkg_manifest=self.manifest)

        if self.manifest.pkg_extcfg:
            self.ext_manager = PkgInstExtrasManager(pkg_manifest=self.manifest)
        else:
            self.ext_manager = None
        LOG.debug(f'{self.msg_src}: {self.manifest.pkg_id.pkg_id}:'
                  f' Installation extras manager: {self.ext_manager}')

        if self.manifest.pkg_svccfg:
            self.svc_manager = WinSvcManagerNSSM(
                svc_conf=self.manifest.pkg_svccfg
            )
        else:
            self.svc_manager = None
        LOG.debug(f'{self.msg_src}: {self.manifest.pkg_id.pkg_id}:'
                  f' Service manager: {self.svc_manager}')

    @property
    def id(self):
        """"""
        return self.manifest.pkg_id

    def handle_config_setup(self, mheading: str=None):
        """Execute steps on setting up package configuration files.

        :param mheading: str, descriptive heading to be added to error/log
                         messages
        """
        mhd_base = f'{self.msg_src}: {self.id.pkg_name}'
        mheading = f'{mheading}: {mhd_base}' if mheading else mhd_base
        LOG.debug(f'{mheading}: Setup configuration: ...')

        try:
            self.cfg_manager.setup_conf()
        except cfgm_exc.PkgConfNotFoundError as e:
            LOG.debug(f'{mheading}: Setup configuration: NOP')
        else:
            LOG.debug(f'{mheading}: Setup configuration: OK')

    def handle_inst_extras(self, mheading: str=None):
        """Process package's extra installation options.

        :param mheading: str, descriptive heading to be added to error/log
                         messages
        """
        mhd_base = f'{self.msg_src}: {self.id.pkg_name}'
        mheading = f'{mheading}: {mhd_base}' if mheading else mhd_base

        if self.ext_manager:
            LOG.debug(f'{mheading}: Handle extra installation options: ...')
            self.ext_manager.handle_install_extras()
            LOG.debug(f'{mheading}: Handle extra installation options: OK')
        else:
            LOG.debug(f'{mheading}: Handle extra installation options: NOP')

    def handle_uninst_extras(self, mheading: str=None):
        """Process package's extra uninstall options.

        :param mheading: str, descriptive heading to be added to error/log
                         messages
        """
        mhd_base = f'{self.msg_src}: {self.id.pkg_name}'
        mheading = f'{mheading}: {mhd_base}' if mheading else mhd_base

        if self.ext_manager:
            LOG.debug(f'{mheading}: Handle extra uninstall options: ...')
            self.ext_manager.handle_uninstall_extras()
            LOG.debug(f'{mheading}: Handle extra uninstall options: OK')
        else:
            LOG.debug(f'{mheading}: Handle extra uninstall options: NOP')

    def handle_svc_setup(self, mheading: str=None):
        """Execute steps on package's service setup.

        :param mheading: str, descriptive heading to be added to error/log
                         messages
        """
        mhd_base = f'{self.msg_src}: {self.id.pkg_name}'
        mheading = f'{mheading}: {mhd_base}' if mheading else mhd_base
        no_svc_marker = 'service does not exist as an installed service.'

        if self.svc_manager:
            svc_name = self.svc_manager.svc_name
            LOG.debug(f'{mheading}: Setup service: {svc_name}: ...')
            try:
                ret_code, stdout, stderr = self.svc_manager.status()
            except svcm_exc.ServiceManagerCommandError as e:
                exc_msg_line = str(e).replace('\n', '').strip()
                LOG.debug(f'{mheading}: Setup service: {svc_name}:'
                          f' Get initial service status: {exc_msg_line}')
                if not exc_msg_line.endswith(no_svc_marker):
                    err_msg = f'{mheading}: Setup service: {svc_name}:' \
                              f' Get initial service status: {e}'
                    raise svcm_exc.ServiceSetupError(err_msg) from e
                # Setup a service
                try:
                    self.svc_manager.setup()
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = f'{mheading}: Setup service: {svc_name}: {e}'
                    raise svcm_exc.ServiceSetupError(err_msg) from e
            else:
                LOG.debug(
                    f'{mheading}: Setup service: {svc_name}: Get initial'
                    f' service status: stdout[{stdout}] stderr[{stderr}]'
                )
                svc_status = str(stdout).strip().rstrip('\n')
                # Wipe existing service
                try:
                    if svc_status != SVC_STATUS.STOPPED:
                        self.svc_manager.stop()

                    self.svc_manager.remove()
                    LOG.debug(f'{mheading}: Wipe existing service:'
                              f' {svc_name}: OK')
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'{mheading}: Wipe existing service:'
                               f' {svc_name}: {e}')
                    raise svcm_exc.ServiceSetupError(err_msg) from e
                # Setup a replacement service
                try:
                    self.svc_manager.setup()
                    ret_code, stdout, stderr = (self.svc_manager.status())
                    svc_status = str(stdout).strip().rstrip('\n')
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'{mheading}: Setup replacement service:'
                               f' {svc_name}: {e}')
                    raise svcm_exc.ServiceSetupError(err_msg) from e
                else:
                    if svc_status != SVC_STATUS.STOPPED:
                        err_msg = (
                            f'{mheading}: Setup replacement service:'
                            f' {svc_name}: Invalid status: {svc_status}'
                        )
                        raise svcm_exc.ServiceSetupError(err_msg)

            LOG.debug(f'{mheading}: Setup service: {svc_name}: OK')
        else:
            LOG.debug(f'{mheading}: Setup service: NOP')

    def handle_svc_wipe(self, mheading: str=None):
        """Execute steps on package's service wipe off.

        :param mheading: str, descriptive heading to be added to error/log
                         messages
        """
        mhd_base = f'{self.msg_src}: {self.id.pkg_name}'
        mheading = f'{mheading}: {mhd_base}' if mheading else mhd_base
        no_svc_marker = 'service does not exist as an installed service.'

        if self.svc_manager:
            svc_name = self.svc_manager.svc_name
            LOG.debug(f'{mheading}: Wipe service: {svc_name}: ...')
            try:
                ret_code, stdout, stderr = self.svc_manager.status()
            except svcm_exc.ServiceManagerCommandError as e:
                exc_msg_line = str(e).replace('\n', '').strip()
                LOG.debug(f'{mheading}: Wipe service: {svc_name}:'
                          f' Get initial service status: {exc_msg_line}')
                if not exc_msg_line.endswith(no_svc_marker):
                    err_msg = f'{mheading}: Wipe service: {svc_name}: {e}'
                    raise svcm_exc.ServiceWipeError(err_msg) from e
                LOG.debug(f'{mheading}: Wipe service: NOP')
            else:
                LOG.debug(
                    f'{mheading}: Wipe service: {svc_name}: Get initial'
                    f' service status: stdout[{stdout}] stderr[{stderr}]'
                )
                svc_status = str(stdout).strip().rstrip('\n')
                # Try to remove existing service
                try:
                    if svc_status != SVC_STATUS.STOPPED:
                        self.svc_manager.stop()

                    self.svc_manager.remove()
                    LOG.debug(f'{mheading}: Wipe service: {svc_name}: OK')
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'{mheading}: Wipe existing service:'
                               f' {svc_name}: {e}')
                    raise svcm_exc.ServiceWipeError(err_msg) from e
        else:
            LOG.debug(f'{mheading}: Wipe service: NOP')

    def handle_svc_start(self, mheading: str=None):
        """Execute steps on package's service start.

        :param mheading: str, descriptive heading to be added to error/log
                         messages
        """
        mhd_base = f'{self.msg_src}: {self.id.pkg_name}'
        mheading = f'{mheading}: {mhd_base}' if mheading else mhd_base
        no_svc_marker = 'service does not exist as an installed service.'
        # TODO: Move stuff from the CmdStart.service_start() method here.
        #       Overall design of this method should resemble one of the
        #       Package.handle_svc_stop() method.

    def handle_svc_stop(self, mheading: str=None):
        """Execute steps on package's service stop.

        :param mheading: str, descriptive heading to be added to error/log
                         messages
        """
        mhd_base = f'{self.msg_src}: {self.id.pkg_name}'
        mheading = f'{mheading}: {mhd_base}' if mheading else mhd_base
        no_svc_marker = 'service does not exist as an installed service.'

        if self.svc_manager:
            svc_name = self.svc_manager.svc_name
            LOG.debug(f'{mheading}: Stop service: {svc_name}: ...')
            try:
                ret_code, stdout, stderr = self.svc_manager.status()
            except svcm_exc.ServiceManagerCommandError as e:
                exc_msg_line = str(e).replace('\n', '').strip()
                LOG.debug(f'{mheading}: Stop service: {svc_name}:'
                          f' Get initial service status: {exc_msg_line}')
                if not exc_msg_line.endswith(no_svc_marker):
                    err_msg = f'{mheading}: Stop service: {svc_name}: {e}'
                    raise svcm_exc.ServiceStopError(err_msg) from e
                LOG.debug(f'{mheading}: Stop service: NOP')
            else:
                LOG.debug(
                    f'{mheading}: Stop service: {svc_name}: Get initial'
                    f' service status: stdout[{stdout}] stderr[{stderr}]'
                )
                svc_status = str(stdout).strip().rstrip('\n')
                # Stop existing service
                try:
                    if svc_status != SVC_STATUS.STOPPED:
                        self.svc_manager.stop()

                    LOG.debug(f'{mheading}: Stop service: {svc_name}: OK')
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = f'{mheading}: Stop service: {svc_name}: {e}'
                    raise svcm_exc.ServiceStopError(err_msg) from e
        else:
            LOG.debug(f'{mheading}: Stop service: NOP')

    def handle_vardata_wipe(self, mheading: str=None):
        """Execute steps on wiping of package's variable data.

        :param mheading: str, descriptive heading to be added to error/log
                         messages
        """
        mhd_base = f'{self.msg_src}: {self.id.pkg_name}'
        mheading = f'{mheading}: {mhd_base}' if mheading else mhd_base

        work_dpath = getattr(self.manifest.istor_nodes, ISTOR_NODE.WORK)
        run_dpath = getattr(self.manifest.istor_nodes, ISTOR_NODE.RUN)

        for host_dpath in work_dpath, run_dpath:
            dpath = host_dpath.joinpath(self.id.pkg_name)
            try:
                cm_utl.rmdir(str(dpath), recursive=True)
                dpath.mkdir(parents=True, exist_ok=True)
                LOG.debug(f'{mheading}: Wipe variable data: {dpath}: OK')
            except (OSError, RuntimeError) as e:
                err_msg = (f'{mheading}: Wipe variable data: {dpath}:'
                           f' {type(e).__name__}: {e}')
                raise cr_exc.RCError(err_msg) from e

    def save_manifest(self, mheading: str=None, dpath: Path=None):
        """Save package's manifest to filesystem.

        :param mheading: str, descriptive heading to be added to error/log
                         messages
        :param dpath:    Path, absolute path to the host directory
                         where to save to
        """
        mhd_base = f'{self.msg_src}: {self.id.pkg_name}'
        mheading = f'{mheading}: {mhd_base}' if mheading else mhd_base

        try:
            cm_utl.rmdir(str(dpath), recursive=True)
            dpath.mkdir(parents=True)
            self.manifest.save(dpath)
        except (OSError, RuntimeError, cr_exc.RCError) as e:
            err_msg = f'{mheading}: Register package: {self.id}: {e}'
            raise cr_exc.RCError(err_msg) from e

    def delete_manifest(self, mheading: str=None, dpath: Path=None):
        """Delete package's manifest from filesystem.

        :param mheading: str, descriptive heading to be added to error/log
                         messages
        :param dpath:    Path, absolute path to the host directory
                         where to delete from
        """
        mhd_base = f'{self.msg_src}: {self.id.pkg_name}'
        mheading = f'{mheading}: {mhd_base}' if mheading else mhd_base

        try:
            self.manifest.delete(dpath)
        except (OSError, RuntimeError, cr_exc.RCError) as e:
            err_msg = f'{mheading}: Deregister package: {self.id}: {e}'
            raise cr_exc.RCError(err_msg) from e
