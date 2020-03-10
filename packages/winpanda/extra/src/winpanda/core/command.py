"""Panda package management for Windows.

DC/OS package management command definitions.
"""
import abc
import os
from pathlib import Path
import shutil
import yaml

from cfgm import exceptions as cfgm_exc
from common import exceptions as cm_exc
from common import logger
from common import storage
from common import utils as cm_utl
from common.cli import CLI_COMMAND, CLI_CMDTARGET, CLI_CMDOPT
from common.storage import ISTOR_NODE
from core import cmdconf
from core import exceptions as cr_exc
from core.istate import ISTATE
from core.package.id import PackageId
from core.package.manifest import PackageManifest
from core.package.package import Package
from core import utils as cr_utl
from extm import exceptions as extm_exc
from svcm import exceptions as svcm_exc
from svcm.nssm import SVC_STATUS


LOG = logger.get_logger(__name__)

CMD_TYPES = {}


def create(**cmd_opts):
    """Instantiate a command.

    :param cmd_opts: dict, command options:
                     {
                         'command_name': <str>,
                         ...
                     }
    """
    command_name = cmd_opts.get(CLI_CMDOPT.CMD_NAME, '')

    return CMD_TYPES[command_name](**cmd_opts)


def command_type(command_name):
    """Register a command class in the command types registry.

    :param command_name: str, name of a command
    """
    def decorator(cls):
        """"""
        CMD_TYPES[command_name] = cls
        return cls

    return decorator


class Command(metaclass=abc.ABCMeta):
    """Abstract base class for command types.
    """
    def __init__(self, **cmd_opts):
        """Constructor."""
        self.msg_src = self.__class__.__name__
        self.cmd_opts = cmd_opts

    def __repr__(self):
        return (
            '<%s(cmd_opts="%s")>' % (self.__class__.__name__, self.cmd_opts)
        )

    def __str__(self):
        return self.__repr__()

    @abc.abstractmethod
    def verify_cmd_options(self, *args, **kwargs):
        """Verify command options."""
        pass

    @abc.abstractmethod
    def execute(self, *args, **kwargs):
        """Execute command."""
        pass


@command_type(CLI_COMMAND.SETUP)
class CmdSetup(Command):
    """Setup command implementation."""
    def __init__(self, **cmd_opts):
        """"""
        super(CmdSetup, self).__init__(**cmd_opts)
        if self.cmd_opts.get(CLI_CMDOPT.CMD_TARGET) == CLI_CMDTARGET.STORAGE:
            # Deactivate cluster-related configuration steps
            self.cmd_opts[CLI_CMDOPT.DCOS_CLUSTERCFGPATH] = 'NOP'

        self.config = cmdconf.create(**self.cmd_opts)

        LOG.debug(f'{self.msg_src}: cmd_opts: {self.cmd_opts}')

    def verify_cmd_options(self):
        """Verify command options."""
        pass

    def execute(self):
        """Execute command."""
        LOG.debug(f'{self.msg_src}: Execute: Target:'
                  f' {self.cmd_opts.get(CLI_CMDOPT.CMD_TARGET)}')

        try:
            cmd_target = self.cmd_opts.get(CLI_CMDOPT.CMD_TARGET)
            if cmd_target == CLI_CMDTARGET.STORAGE:
                # (Re)build/repair the installation storage structure.
                self.config.inst_storage.construct(
                    clean=self.cmd_opts.get(CLI_CMDOPT.INST_CLEAN)
                )
            elif cmd_target == CLI_CMDTARGET.PKGALL:
                istate = self.config.inst_state.istate
                if istate == ISTATE.INSTALLATION_IN_PROGRESS:
                    self._handle_cmdtarget_pkgall()
                    self._register_istate(ISTATE.INSTALLED)
                else:
                    LOG.info(
                        f'{self.msg_src}: Execute: Invalid DC/OS installation'
                        f' state detected: {istate}: NOP'
                    )

            LOG.info(f'{self.msg_src}: Execute: OK')
        except cm_exc.WinpandaError:
            self._register_istate(ISTATE.INSTALLATION_FAILED)
            raise

    def _register_istate(self, inst_state):
        """"""
        # TODO: Move this method to the abstract base parent class Command to
        #       avoid code duplication in command manager classes.
        msg_base = (f'{self.msg_src}:'
                    f' Execute: Register installation state: {inst_state}')
        try:
            self.config.inst_state.istate = inst_state
            LOG.debug(f'{msg_base}: OK')
        except cr_exc.RCError as e:
            raise cr_exc.SetupCommandError(f'Execute: {type(e).__name__}: {e}')

    def _handle_cmdtarget_pkgall(self):
        """"""
        # TODO: This code is duplicated in the CmdUpgrade._handle_clean_setup()
        #       stuff and so should be made standalone to be reused in both
        #       classes avoiding massive code duplication.
        dstor_root_url = self.config.cluster_conf.get(
            'distribution-storage', {}
        ).get('rooturl', '')
        dstor_pkgrepo_path = self.config.cluster_conf.get(
            'distribution-storage', {}
        ).get('pkgrepopath', '')

        # Add packages to the local package repository and initialize their
        # manager objects
        packages_bulk = {}

        for item in self.config.ref_pkg_list:
            pkg_id = PackageId(pkg_id=item)

            try:
                self.config.inst_storage.add_package(
                    pkg_id=pkg_id,
                    dstor_root_url=dstor_root_url,
                    dstor_pkgrepo_path=dstor_pkgrepo_path
                )
            except cr_exc.RCError as e:
                err_msg = (f'{self.msg_src}: Execute: Add package to local'
                           f' repository: {pkg_id.pkg_id}: {e}')
                raise cr_exc.SetupCommandError(err_msg) from e

            try:
                package = Package(
                    pkg_id=pkg_id,
                    istor_nodes=self.config.inst_storage.istor_nodes,
                    cluster_conf=self.config.cluster_conf,
                    extra_context=self.config.dcos_conf.get('values')
                )
            except cr_exc.RCError as e:
                err_msg = (f'{self.msg_src}: Execute: Initialize package:'
                           f' {pkg_id.pkg_id}: {e}')
                raise cr_exc.SetupCommandError(err_msg) from e

            packages_bulk[pkg_id.pkg_name] = package

        # Finalize package setup procedures taking package mutual
        # dependencies into account.

        packages_sorted_by_deps = cr_utl.pkg_sort_by_deps(packages_bulk)

        # Prepare base per package configuration objects
        for package in packages_sorted_by_deps:
            # TODO: This method moves parts of individual packages which should
            #       be shared with other packages to DC/OS installation shared
            #       directories (<inst_root>\[bin|etc|lib]). It should be
            #       redesigned to deal with only required parts of packages and
            #       not populating shared DC/OS installation directories with
            #       unnecessary stuff.
            self._handle_pkg_dir_setup(package)
            # TODO: This should be replaced with Package.handle_config_setup()
            #       method to avoid code duplication in command manager classes
            #       CmdSetup and CmdUpgrade
            self._handle_pkg_cfg_setup(package)

        # Deploy DC/OS aggregated configuration object
        self._deploy_dcos_conf()

        # Run per package extra installation helpers, setup services and
        # save manifests
        for package in packages_sorted_by_deps:
            # TODO: This should be replaced with Package.handle_inst_extras()
            #       method to avoid code duplication in command manager classes
            #       CmdSetup and CmdUpgrade
            self._handle_pkg_inst_extras(package)
            # TODO: This should be replaced with Package.handle_svc_setup()
            #       method to avoid code duplication in command manager classes
            #       CmdSetup and CmdUpgrade
            self._handle_pkg_svc_setup(package)

            # TODO: This part should be replaced with Package.save_manifest()
            #       method to avoid code duplication in command manager classes
            #       CmdSetup and CmdUpgrade
            try:
                package.manifest.save()
            except cr_exc.RCError as e:
                err_msg = (f'{self.msg_src}: Execute: Register package:'
                           f' {package.manifest.pkg_id.pkg_id}: {e}')
                raise cr_exc.SetupCommandError(err_msg)

            LOG.info(f'{self.msg_src}: Setup package:'
                     f' {package.manifest.pkg_id.pkg_id}: OK')

    def _handle_pkg_dir_setup(self, package):
        """Transfer files from special directories into location.

        :param package: Package, DC/OS package manager object
        """
        # TODO: Move this functionality to a method of the Package class and
        #       reuse it in CmdSetup and CmdUpgrade classes to avoid code
        #       duplication.
        pkg_path = getattr(
            package.manifest.istor_nodes, ISTOR_NODE.PKGREPO
        ).joinpath(package.manifest.pkg_id.pkg_id)
        root = getattr(
            package.manifest.istor_nodes, ISTOR_NODE.ROOT
        )

        for name in ('bin', 'etc', 'include', 'lib'):
            srcdir = pkg_path / name
            if srcdir.exists():
                dstdir = root / name
                dstdir.mkdir(exist_ok=True)
                cm_utl.transfer_files(str(srcdir), str(dstdir))

    def _handle_pkg_cfg_setup(self, package):
        """Execute steps on package configuration files setup.

        :param package: Package, DC/OS package manager object
        """
        # TODO: This method should be removed after transition to use of
        #       Package.handle_config_setup()
        pkg_id = package.manifest.pkg_id

        LOG.debug(f'{self.msg_src}: Execute: {pkg_id.pkg_name}: Setup'
                  f' configuration: ...')
        try:
            package.cfg_manager.setup_conf()
        except cfgm_exc.PkgConfNotFoundError as e:
            LOG.debug(f'{self.msg_src}: Execute: {pkg_id.pkg_name}: Setup'
                      f' configuration: NOP')
        except cfgm_exc.PkgConfManagerError as e:
            err_msg = (f'Execute: {pkg_id.pkg_name}: Setup configuration:'
                       f'{type(e).__name__}: {e}')
            raise cr_exc.SetupCommandError(err_msg) from e
        else:
            LOG.debug(f'{self.msg_src}: Execute: {pkg_id.pkg_name}: Setup'
                      f' configuration: OK')

    def _handle_pkg_inst_extras(self, package):
        """Process package extra installation options.

        :param package: Package, DC/OS package manager object
        """
        # TODO: This method should be removed after transition to use of
        #       Package.handle_inst_extras()
        msg_src = self.__class__.__name__
        pkg_id = package.manifest.pkg_id

        if package.ext_manager:
            LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}:'
                      f' Handle extra installation options: ...')
            try:
                package.ext_manager.handle_install_extras()
            except extm_exc.InstExtrasManagerError as e:
                err_msg = (f'Execute: {pkg_id.pkg_name}:'
                           f' Handle extra installation options: {e}')
                raise cr_exc.SetupCommandError(err_msg) from e

            LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}:'
                      f' Handle extra installation options: OK')
        else:
            LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}:'
                      f' Handle extra installation options: NOP')

    def _handle_pkg_svc_setup(self, package):
        """Execute steps on package service setup.

        :param package: Package, DC/OS package manager object
        """
        # TODO: This method should be removed after transition to use of
        #       Package.handle_svc_setup()
        msg_src = self.__class__.__name__
        pkg_id = package.manifest.pkg_id

        if package.svc_manager:
            svc_name = package.svc_manager.svc_name
            LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Setup service:'
                      f' {svc_name}: ...')
            try:
                ret_code, stdout, stderr = package.svc_manager.status()
            except svcm_exc.ServiceManagerCommandError as e:
                LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Setup'
                          f' service: Get initial service status: {svc_name}:'
                          f' {e}')
                # Try to setup, as a service (expectedly) doesn't exist and
                # checking it's status naturally would yield an error.
                try:
                    package.svc_manager.setup()
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'Execute: {pkg_id.pkg_name}: Setup service:'
                               f' {svc_name}: {e}')
                    raise cr_exc.SetupCommandError(err_msg) from e
            else:
                LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Setup'
                          f' service: Get initial service status: {svc_name}:'
                          f' stdout[{stdout}] stderr[{stderr}]')
                svc_status = str(stdout).strip().rstrip('\n')
                # Try to remove existing service
                try:
                    if svc_status == SVC_STATUS.RUNNING:
                        package.svc_manager.stop()

                    package.svc_manager.remove()
                    LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Remove'
                              f' existing service: {svc_name}: OK')
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'Execute: {pkg_id.pkg_name}: Remove existing'
                               f' service: {svc_name}: {e}')
                    raise cr_exc.SetupCommandError(err_msg) from e
                # Setup a replacement service
                try:
                    package.svc_manager.setup()
                    ret_code, stdout, stderr = (package.svc_manager.status())
                    svc_status = str(stdout).strip().rstrip('\n')
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'Execute: {pkg_id.pkg_name}: Setup replacement'
                               f' service: {svc_name}: {e}')
                    raise cr_exc.SetupCommandError(err_msg) from e
                else:
                    if svc_status != SVC_STATUS.STOPPED:
                        err_msg = (f'Execute: {pkg_id.pkg_name}: Setup'
                                   f' replacement service: {svc_name}:'
                                   f' Invalid status: {svc_status}')
                        raise cr_exc.SetupCommandError(err_msg)

            LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Setup service:'
                      f' {svc_name}: OK')
        else:
            LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Setup service:'
                      f' NOP')

    def _deploy_dcos_conf(self):
        """Deploy aggregated DC/OS configuration object."""
        # TODO: This should be made standalone and then reused in command
        #       manager classes CmdSetup and CmdUpgrade to avoid code
        #       duplication
        LOG.debug(f'{self.msg_src}: Execute: Deploy aggregated config: ...')

        template = self.config.dcos_conf.get('template')
        values = self.config.dcos_conf.get('values')

        rendered = template.render(values)
        config = yaml.safe_load(rendered)

        assert config.keys() == {"package"}

        # Write out the individual files
        for file_info in config["package"]:
            assert file_info.keys() <= {"path", "content", "permissions"}
            path = Path(file_info['path'].replace('\\', os.path.sep))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(file_info['content'] or '')
            # On Windows, we don't interpret permissions yet

        LOG.debug(f'{self.msg_src}: Execute: Deploy aggregated config: OK')


@command_type(CLI_COMMAND.UPGRADE)
class CmdUpgrade(Command):
    """Implementation of the Upgrade command manager."""
    def __init__(self, **cmd_opts):
        """"""
        super(CmdUpgrade, self).__init__(**cmd_opts)

        self.config = cmdconf.create(**self.cmd_opts)

        LOG.debug(f'{self.msg_src}: cmd_opts: {self.cmd_opts}')

    def verify_cmd_options(self):
        """Verify command options."""
        pass

    def execute(self):
        """Execute command."""
        LOG.debug(f'{self.msg_src}: Execute ...')

        try:
            istate = self.config.inst_state.istate
            if istate == ISTATE.UPGRADE_IN_PROGRESS:
                self._handle_upgrade()
                self._register_istate(ISTATE.INSTALLED)
            else:
                LOG.info(
                    f'{self.msg_src}: Execute: Invalid DC/OS installation'
                    f' state detected: {istate}: NOP'
                )

            LOG.info(f'{self.msg_src}: Execute: OK')
        except cm_exc.WinpandaError:
            self._register_istate(ISTATE.UPGRADE_FAILED)
            raise

    def _register_istate(self, inst_state):
        """"""
        # TODO: Move this method to the abstract base parent class Command to
        #       avoid code duplication in command manager classes.
        msg_base = (f'{self.msg_src}:'
                    f' Execute: Register installation state: {inst_state}')
        try:
            self.config.inst_state.istate = inst_state
            LOG.debug(f'{msg_base}: OK')
        except cr_exc.RCError as e:
            raise cr_exc.SetupCommandError(f'Execute: {type(e).__name__}: {e}')

    def _handle_upgrade(self):
        """"""
        self._handle_upgrade_pre()
        self._handle_teardown()
        self._handle_teardown_post()
        self._handle_clean_setup()

    def _handle_upgrade_pre(self):
        """"""
        mheading = f'{self.msg_src}: Execute'
        # TODO: Add all the upgrade preparation steps (package download,
        # TODO: rendering configs, etc.) here. I.e. everything that can be
        # TODO: done without affecting the currently running system.

    def _handle_teardown(self):
        """Teardown the currently installed DC/OS."""
        mheading = f'{self.msg_src}: Execute'
        pkg_manifests = (
            self.config.inst_storage.get_pkgactive(PackageManifest.load)
        )
        packages_bulk = {
            m.pkg_id.pkg_name: Package(manifest=m) for m in pkg_manifests
        }

        iroot_dpath = self.config.inst_storage.root_dpath
        itmp_dpath = self.config.inst_storage.tmp_dpath
        pkgactive_old_dpath = itmp_dpath.joinpath(
            f'{storage.DCOS_PKGACTIVE_DPATH_DFT}.old'
        )
        sh_conf_dname = storage.DCOS_INST_CFG_DPATH_DFT
        sh_exec_dname = storage.DCOS_INST_BIN_DPATH_DFT
        sh_lib__dname = storage.DCOS_INST_LIB_DPATH_DFT

        # Teardown installed packages
        for package in cr_utl.pkg_sort_by_deps(packages_bulk):
            package.handle_svc_wipe(mheading)
            package.handle_uninst_extras(mheading)
            package.handle_vardata_wipe(mheading)
            package.save_manifest(mheading, pkgactive_old_dpath)
            package.delete_manifest(mheading)

        # Remove/preserve shared directories
        for dname in sh_conf_dname, sh_exec_dname, sh_lib__dname:
            active_dpath = iroot_dpath.joinpath(dname)
            preserve_dpath = itmp_dpath.joinpath(f'{dname}.old')
            try:
                active_dpath.rename(preserve_dpath)
            except (OSError, RuntimeError) as e:
                err_msg = (f'{mheading}: Preserve shared directory:'
                           f' {active_dpath}: {type(e).__name__}: {e}')
                raise cr_exc.RCError(err_msg) from e

            LOG.debug(f'{mheading}: Preserve hared directory: {active_dpath}:'
                      f' {preserve_dpath}')

    def _handle_teardown_post(self):
        """Perform extra steps on cleaning up unplanned (diverging from initial
        winpanda design and so, not removed by normal teardown procedure) DC/OS
        installation leftovers (see the CmdSetup._handle_pkg_dir_setup() and
        workaround for dcos-diagnostics part in the
        InstallationStorage.add_package()).
        """
        mheading = f'{self.msg_src}: Execute'
        LOG.debug(f'{mheading}: After steps: ...')

        iroot_dpath = self.config.inst_storage.root_dpath
        ivar_dpath = self.config.inst_storage.var_dpath
        itmp_dpath = self.config.inst_storage.tmp_dpath

        wipe_dirs = [
            iroot_dpath.joinpath('include'),
            iroot_dpath.joinpath('mesos-logs'),
            ivar_dpath.joinpath('lib'),
        ]

        for dpath in wipe_dirs:
            try:
                cm_utl.rmdir(str(dpath), recursive=True)
                LOG.debug(f'{mheading}: After steps: Remove dir: {dpath}: OK')
            except (OSError, RuntimeError) as e:
                LOG.warning(f'{mheading}: After steps: Remove dir: {dpath}:'
                            f' {type(e).__name__}: {e}')

        wipe_files = [
            iroot_dpath.joinpath('dcos-diagnostics.exe'),
            iroot_dpath.joinpath('servicelist.txt'),
        ]

        for fpath in wipe_files:
            try:
                fpath.unlink()
                LOG.debug(f'{mheading}: After steps: Remove file: {fpath}: OK')
            except (OSError, RuntimeError) as e:
                LOG.warning(f'{mheading}: After steps: Remove file: {fpath}:'
                            f' {type(e).__name__}: {e}')

        # Restoreobjects created/populated by entities/processes outside
        # of winpanda routines, but required for winpanda to do it's stuff.

        restore_dirs = [
            iroot_dpath.joinpath('bin'),
            iroot_dpath.joinpath('etc'),
        ]

        for dpath in restore_dirs:
            try:
                dpath.mkdir(parents=True, exist_ok=True)
                LOG.debug(f'{mheading}: After steps: Restore dir: {dpath}: OK')
            except (OSError, RuntimeError) as e:
                LOG.warning(f'{mheading}: After steps: Restore dir: {dpath}:'
                            f' {type(e).__name__}: {e}')

        restore_files = [
            (itmp_dpath.joinpath('bin.old', 'detect_ip.ps1'),
             iroot_dpath.joinpath('bin')),
            (itmp_dpath.joinpath('bin.old', 'detect_ip_public.ps1'),
             iroot_dpath.joinpath('bin')),
            (itmp_dpath.joinpath('bin.old', 'fault-domain-detect-win.ps1'),
             iroot_dpath.joinpath('bin')),
            (itmp_dpath.joinpath('etc.old', 'cluster.conf'),
             iroot_dpath.joinpath('etc')),
            (itmp_dpath.joinpath('etc.old', 'paths.json'),
             iroot_dpath.joinpath('etc')),
        ]

        for fspec in restore_files:
            try:
                shutil.copy(str(fspec[0]), str(fspec[1]), follow_symlinks=False)
                LOG.debug(f'{mheading}: After steps: Restore file: {fspec}: OK')
            except (OSError, RuntimeError) as e:
                LOG.warning(f'{mheading}: After steps: Restore file: {fspec}:'
                            f' {type(e).__name__}: {e}')

        LOG.debug(f'{mheading}: After steps: OK')

    def _handle_clean_setup(self):
        """Perform all the steps on DC/OS installation remaining after the
        preparation stage is done (the CmdUpgrade._handle_upgrade_pre()).
        """
        # TODO: This code duplicates the CmdSetup._handle_cmdtarget_pkgall()
        #       stuff and so should be made standalone to be reused in both
        #       classes avoiding massive code duplication.
        mheading = f'{self.msg_src}: Execute'
        dstor_root_url = self.config.cluster_conf.get(
            'distribution-storage', {}
        ).get('rooturl', '')
        dstor_pkgrepo_path = self.config.cluster_conf.get(
            'distribution-storage', {}
        ).get('pkgrepopath', '')

        # Add packages to the local package repository and initialize their
        # manager objects
        packages_bulk = {}

        for item in self.config.ref_pkg_list:
            pkg_id = PackageId(pkg_id=item)

            try:
                self.config.inst_storage.add_package(
                    pkg_id=pkg_id,
                    dstor_root_url=dstor_root_url,
                    dstor_pkgrepo_path=dstor_pkgrepo_path
                )
            except cr_exc.RCError as e:
                err_msg = (f'{self.msg_src}: Execute: Add package to local'
                           f' repository: {pkg_id.pkg_id}: {e}')
                raise cr_exc.SetupCommandError(err_msg) from e

            try:
                package = Package(
                    pkg_id=pkg_id,
                    istor_nodes=self.config.inst_storage.istor_nodes,
                    cluster_conf=self.config.cluster_conf,
                    extra_context=self.config.dcos_conf.get('values')
                )
            except cr_exc.RCError as e:
                err_msg = (f'{self.msg_src}: Execute: Initialize package:'
                           f' {pkg_id.pkg_id}: {e}')
                raise cr_exc.SetupCommandError(err_msg) from e

            packages_bulk[pkg_id.pkg_name] = package

        # Finalize package setup procedures taking package mutual
        # dependencies into account.

        packages_sorted_by_deps = cr_utl.pkg_sort_by_deps(packages_bulk)

        # Prepare base per package configuration objects
        for package in packages_sorted_by_deps:
            # TODO: This method moves parts of individual packages which should
            #       be shared with other packages to DC/OS installation shared
            #       directories (<inst_root>\[bin|etc|lib]). It should be
            #       redesigned to deal with only required parts of packages and
            #       not populating shared DC/OS installation directories with
            #       unnecessary stuff.
            self._handle_pkg_dir_setup(package)
            # TODO: This should be replaced with Package.handle_config_setup()
            #       method to avoid code duplication in command manager classes
            #       CmdSetup and CmdUpgrade
            self._handle_pkg_cfg_setup(package)

        # Deploy DC/OS aggregated configuration object
        self._deploy_dcos_conf()

        # Run per package extra installation helpers, setup services and
        # save manifests
        for package in packages_sorted_by_deps:
            # TODO: This should be replaced with Package.handle_inst_extras()
            #       method to avoid code duplication in command manager classes
            #       CmdSetup and CmdUpgrade
            self._handle_pkg_inst_extras(package)
            # TODO: This should be replaced with Package.handle_svc_setup()
            #       method to avoid code duplication in command manager classes
            #       CmdSetup and CmdUpgrade
            self._handle_pkg_svc_setup(package)

            # TODO: This part should be replaced with Package.save_manifest()
            #       method to avoid code duplication in command manager classes
            #       CmdSetup and CmdUpgrade
            try:
                package.manifest.save()
            except cr_exc.RCError as e:
                err_msg = (f'{self.msg_src}: Execute: Register package:'
                           f' {package.manifest.pkg_id.pkg_id}: {e}')
                raise cr_exc.SetupCommandError(err_msg)

            LOG.info(f'{self.msg_src}: Setup package:'
                     f' {package.manifest.pkg_id.pkg_id}: OK')

    def _handle_pkg_dir_setup(self, package):
        """Transfer files from special directories into location.

        :param package: Package, DC/OS package manager object
        """
        # TODO: Move this functionality to a method of the Package class and
        #       reuse it in CmdSetup and CmdUpgrade classes to avoid code
        #       duplication.
        pkg_path = getattr(
            package.manifest.istor_nodes, ISTOR_NODE.PKGREPO
        ).joinpath(package.manifest.pkg_id.pkg_id)
        root = getattr(
            package.manifest.istor_nodes, ISTOR_NODE.ROOT
        )

        for name in ('bin', 'etc', 'include', 'lib'):
            srcdir = pkg_path / name
            if srcdir.exists():
                dstdir = root / name
                dstdir.mkdir(exist_ok=True)
                cm_utl.transfer_files(str(srcdir), str(dstdir))

    def _handle_pkg_cfg_setup(self, package):
        """Execute steps on package configuration files setup.

        :param package: Package, DC/OS package manager object
        """
        # TODO: This method should be removed after transition to use of
        #       Package.handle_config_setup()
        pkg_id = package.manifest.pkg_id

        LOG.debug(f'{self.msg_src}: Execute: {pkg_id.pkg_name}: Setup'
                  f' configuration: ...')
        try:
            package.cfg_manager.setup_conf()
        except cfgm_exc.PkgConfNotFoundError as e:
            LOG.debug(f'{self.msg_src}: Execute: {pkg_id.pkg_name}: Setup'
                      f' configuration: NOP')
        except cfgm_exc.PkgConfManagerError as e:
            err_msg = (f'Execute: {pkg_id.pkg_name}: Setup configuration:'
                       f'{type(e).__name__}: {e}')
            raise cr_exc.SetupCommandError(err_msg) from e
        else:
            LOG.debug(f'{self.msg_src}: Execute: {pkg_id.pkg_name}: Setup'
                      f' configuration: OK')

    def _handle_pkg_inst_extras(self, package):
        """Process package extra installation options.

        :param package: Package, DC/OS package manager object
        """
        # TODO: This method should be removed after transition to use of
        #       Package.handle_inst_extras()
        msg_src = self.__class__.__name__
        pkg_id = package.manifest.pkg_id

        if package.ext_manager:
            LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}:'
                      f' Handle extra installation options: ...')
            try:
                package.ext_manager.handle_install_extras()
            except extm_exc.InstExtrasManagerError as e:
                err_msg = (f'Execute: {pkg_id.pkg_name}:'
                           f' Handle extra installation options: {e}')
                raise cr_exc.SetupCommandError(err_msg) from e

            LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}:'
                      f' Handle extra installation options: OK')
        else:
            LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}:'
                      f' Handle extra installation options: NOP')

    def _handle_pkg_svc_setup(self, package):
        """Execute steps on package service setup.

        :param package: Package, DC/OS package manager object
        """
        # TODO: This method should be removed after transition to use of
        #       Package.handle_svc_setup()
        msg_src = self.__class__.__name__
        pkg_id = package.manifest.pkg_id

        if package.svc_manager:
            svc_name = package.svc_manager.svc_name
            LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Setup service:'
                      f' {svc_name}: ...')
            try:
                ret_code, stdout, stderr = package.svc_manager.status()
            except svcm_exc.ServiceManagerCommandError as e:
                LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Setup'
                          f' service: Get initial service status: {svc_name}:'
                          f' {e}')
                # Try to setup, as a service (expectedly) doesn't exist and
                # checking it's status naturally would yield an error.
                try:
                    package.svc_manager.setup()
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'Execute: {pkg_id.pkg_name}: Setup service:'
                               f' {svc_name}: {e}')
                    raise cr_exc.SetupCommandError(err_msg) from e
            else:
                LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Setup'
                          f' service: Get initial service status: {svc_name}:'
                          f' stdout[{stdout}] stderr[{stderr}]')
                svc_status = str(stdout).strip().rstrip('\n')
                # Try to remove existing service
                try:
                    if svc_status == SVC_STATUS.RUNNING:
                        package.svc_manager.stop()

                    package.svc_manager.remove()
                    LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Remove'
                              f' existing service: {svc_name}: OK')
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'Execute: {pkg_id.pkg_name}: Remove existing'
                               f' service: {svc_name}: {e}')
                    raise cr_exc.SetupCommandError(err_msg) from e
                # Setup a replacement service
                try:
                    package.svc_manager.setup()
                    ret_code, stdout, stderr = (package.svc_manager.status())
                    svc_status = str(stdout).strip().rstrip('\n')
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'Execute: {pkg_id.pkg_name}: Setup replacement'
                               f' service: {svc_name}: {e}')
                    raise cr_exc.SetupCommandError(err_msg) from e
                else:
                    if svc_status != SVC_STATUS.STOPPED:
                        err_msg = (f'Execute: {pkg_id.pkg_name}: Setup'
                                   f' replacement service: {svc_name}:'
                                   f' Invalid status: {svc_status}')
                        raise cr_exc.SetupCommandError(err_msg)

            LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Setup service:'
                      f' {svc_name}: OK')
        else:
            LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Setup service:'
                      f' NOP')

    def _deploy_dcos_conf(self):
        """Deploy aggregated DC/OS configuration object."""
        # TODO: This should be made standalone and then reused in command
        #       manager classes CmdSetup and CmdUpgrade to avoid code
        #       duplication
        LOG.debug(f'{self.msg_src}: Execute: Deploy aggregated config: ...')

        template = self.config.dcos_conf.get('template')
        values = self.config.dcos_conf.get('values')

        rendered = template.render(values)
        config = yaml.safe_load(rendered)

        assert config.keys() == {"package"}

        # Write out the individual files
        for file_info in config["package"]:
            assert file_info.keys() <= {"path", "content", "permissions"}
            path = Path(file_info['path'].replace('\\', os.path.sep))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(file_info['content'] or '')
            # On Windows, we don't interpret permissions yet

        LOG.debug(f'{self.msg_src}: Execute: Deploy aggregated config: OK')

@command_type(CLI_COMMAND.START)
class CmdStart(Command):
    """Start command implementation."""
    def __init__(self, **cmd_opts):
        """Constructor."""
        self.msg_src = self.__class__.__name__
        super(CmdStart, self).__init__(**cmd_opts)

        self.config = cmdconf.create(**self.cmd_opts)
        LOG.debug(f'{self.msg_src}: cmd_opts: {self.cmd_opts}')

    def verify_cmd_options(self):
        """Verify command options."""
        pass

    def execute(self):
        """Execute command."""
        # TODO: Implement DC/OS installation state detection here (alike how
        #       it's done in CmdSetup.execute() or CmdSetup.execute()) to
        #       allow attempts to start services only if
        #       istate == ISTATE.INSTALLED:

        pkg_manifests = (
            self.config.inst_storage.get_pkgactive(PackageManifest.load)
        )
        packages_bulk = {
            m.pkg_id.pkg_name: Package(manifest=m) for m in pkg_manifests
        }

        for package in cr_utl.pkg_sort_by_deps(packages_bulk):
            pkg_id = package.manifest.pkg_id
            mheading = f'{self.msg_src}: Execute: {pkg_id.pkg_name}'

            # TODO: This part should be replaced with
            #       Package.handle_svc_start() method
            if package.svc_manager:
                svc_name = package.svc_manager.svc_name
                LOG.debug(f'{mheading}: Start service: {svc_name}: ...')

                try:
                    self.service_start(package.svc_manager)
                except (svcm_exc.ServiceError,
                        svcm_exc.ServiceManagerError) as e:
                    LOG.error(f'{mheading}: Start service:'
                              f' {type(e).__name__}: {e}')
                else:
                    LOG.debug(f'{mheading}: Start service: {svc_name}: OK')
            else:
                LOG.debug(f'{mheading}: Start service: NOP')

    @cm_utl.retry_on_exc((svcm_exc.ServiceManagerCommandError,
                          svcm_exc.ServiceTransientError), max_attempts=3)
    def service_start(self, svc_manager):
        """Start a system service.

        :param svc_manager: WindowsServiceManager, service manager object
        """
        # TODO: Functionality of this method should be moved to the
        #       Package.handle_svc_start() method
        svc_name = svc_manager.svc_name

        # Discover initial service status
        try:
            ret_code, stdout, stderr = svc_manager.status()
        except svcm_exc.ServiceManagerCommandError as e:
            err_msg = f'Get initial service status: {svc_name}: {e}'
            raise type(e)(err_msg) from e  # Subject to retry
        else:
            log_msg = (f'Get initial service status: {svc_name}:'
                       f'stdout[{stdout}] stderr[{stderr}]')
            LOG.debug(log_msg)
            svc_status = str(stdout).strip().rstrip('\n')

        # Manage service appropriately to its status
        if svc_status == SVC_STATUS.STOPPED:
            # Start a service
            try:
                svc_manager.start()
            except svcm_exc.ServiceManagerCommandError as e:
                err_msg = f'Start service: {svc_name}: {e}'
                raise type(e)(err_msg) from e  # Subject to retry
            # Verify that service is running
            try:
                ret_code, stdout, stderr = svc_manager.status()
                LOG.debug(f'Get final service status: {svc_name}:'
                          f'stdout[{stdout}] stderr[{stderr}]')
                svc_status = str(stdout).strip().rstrip('\n')

                if svc_status == SVC_STATUS.START_PENDING:
                    msg = f'Service is starting: {svc_name}'
                    LOG.debug(msg)
                    raise svcm_exc.ServiceTransientError(msg)  # Subject to retry
                elif svc_status != SVC_STATUS.RUNNING:
                    err_msg = (f'Start service: {svc_name}: Failed:'
                               f' {svc_status}')
                    raise svcm_exc.ServicePersistentError(err_msg)
            except svcm_exc.ServiceManagerCommandError as e:
                err_msg = f'Get final service status: {svc_name}: {e}'
                raise type(e)(err_msg) from e  # Subject to retry
        elif svc_status == SVC_STATUS.START_PENDING:
            msg = f'Service is starting: {svc_name}: ...'
            LOG.debug(msg)
            raise svcm_exc.ServiceTransientError(msg)  # Subject to retry
        elif svc_status == SVC_STATUS.RUNNING:
            LOG.debug(f'Service is already running: {svc_name}')
        else:
            err_msg = f'Invalid service status: {svc_name}: {svc_status}'
            raise svcm_exc.ServicePersistentError(err_msg)
