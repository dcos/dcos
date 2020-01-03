"""Panda package management for Windows.

DC/OS package management command definitions.
"""
import abc
from pathlib import Path

import jinja2 as j2

from cfgm import exceptions as cfgm_exc
from common import logger
from common.cli import CLI_COMMAND, CLI_CMDTARGET, CLI_CMDOPT
from common import utils as cm_utl
from common.storage import ISTOR_NODE
from core import cmdconf
from core import exceptions as cr_exc
from core.package.id import PackageId
from core.package.manifest import PackageManifest
from core.package.package import Package
from core.rc_ctx import ResourceContext
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
        self.msg_src = self.__class__.__name__
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

        if self.cmd_opts.get(CLI_CMDOPT.CMD_TARGET) == CLI_CMDTARGET.STORAGE:
            # (Re)build/repair the installation storage structure.
            self.config.inst_storage.construct(
                clean=self.cmd_opts.get(CLI_CMDOPT.INST_CLEAN)
            )
        elif self.cmd_opts.get(CLI_CMDOPT.CMD_TARGET) == CLI_CMDTARGET.PKGALL:
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
                self._handle_pkg_dir_setup(package)
                self._handle_pkg_cfg_setup(package)

            # Deploy DC/OS aggregated configuration object
            self._deploy_dcos_conf()

            # Run per package extra installation helpers, setup services and
            # save manifests
            for package in packages_sorted_by_deps:
                self._handle_pkg_inst_extras(package)
                self._handle_pkg_svc_setup(package)

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
        msg_src = self.__class__.__name__

        if package.ext_manager:
            LOG.debug(f'{msg_src}: Execute: Handle extra install options:'
                      f' {package.manifest.pkg_id.pkg_name}: ...')
            try:
                package.ext_manager.handle_install_extras()
            except extm_exc.InstExtrasManagerError as e:
                err_msg = (f'Execute: Handle extra install options:'
                           f' {package.manifest.pkg_id.pkg_name}: {e}')
                raise cr_exc.SetupCommandError(err_msg) from e

            LOG.debug(f'{msg_src}: Execute: Handle extra install options:'
                      f' {package.manifest.pkg_id.pkg_name}: OK')
        else:
            LOG.debug(f'{msg_src}: Execute: Handle extra install options:'
                      f' {package.manifest.pkg_id.pkg_name}: NOP')

    def _handle_pkg_svc_setup(self, package):
        """Execute steps on package service setup.

        :param package: Package, DC/OS package manager object
        """
        msg_src = self.__class__.__name__
        pkg_id = package.manifest.pkg_id

        if package.svc_manager:
            svc_name = package.svc_manager.svc_name
            LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Setup service:'
                      f' {svc_name}: ...')
            try:
                ret_code, stdout, stderr = package.svc_manager.status()
            except svcm_exc.ServiceManagerCommandError as e:
                LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Get initial'
                          f' service status: {svc_name}: {e}')
                # Try to setup, as a service (expectedly) doesn't exist and
                # checking it's status naturally would yield an error.
                try:
                    package.svc_manager.setup()
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'Execute: {pkg_id.pkg_name}: Setup service:'
                               f' {svc_name}: {e}')
                    raise cr_exc.SetupCommandError(err_msg) from e
            else:
                LOG.debug(f'{msg_src}: Execute: {pkg_id.pkg_name}: Get initial'
                          f' service status: {svc_name}:'
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
        LOG.debug(f'{self.msg_src}: Execute: Deploy aggregated config: ...')

        context = ResourceContext(
            istor_nodes=self.config.inst_storage.istor_nodes,
            cluster_conf=self.config.cluster_conf,
            extra_values=self.config.dcos_conf.get('values')
        )
        context_items = context.get_items()
        context_items_jr = context.get_items(json_ready=True)

        t_elements = self.config.dcos_conf.get('template').get('package', [])
        for t_element in t_elements:
            path = t_element.get('path')
            content = t_element.get('content')

            try:
                j2t = j2.Environment().from_string(path)
                rendered_path = j2t.render(**context_items)
                dst_fpath = Path(rendered_path)
                j2t = j2.Environment().from_string(content)
                if '.json' in dst_fpath.suffixes[-1:]:
                    rendered_content = j2t.render(**context_items_jr)
                else:
                    rendered_content = j2t.render(**context_items)
            except j2.TemplateError as e:
                err_msg = (
                    f'Execute: Deploy aggregated config: Render:'
                    f' {path}: {type(e).__name__}: {e}'
                )
                raise cfgm_exc.PkgConfFileInvalidError(err_msg) from e

            if not dst_fpath.parent.exists():
                try:
                    dst_fpath.parent.mkdir(parents=True, exist_ok=True)
                    LOG.debug(f'{self.msg_src}: Execute: Deploy aggregated'
                              f' config: Create directory:'
                              f' {dst_fpath.parent}: OK')
                except (OSError, RuntimeError) as e:
                    err_msg = (f'Execute: Deploy aggregated config: Create'
                               f' directory: {dst_fpath.parent}:'
                               f' {type(e).__name__}: {e}')
                    raise cr_exc.SetupCommandError(err_msg) from e
            elif not dst_fpath.parent.is_dir():
                err_msg = (f'Execute: Deploy aggregated config: Save content:'
                           f' {dst_fpath}: Existing parent is not a directory:'
                           f' {dst_fpath.parent}')
                raise cr_exc.SetupCommandError(err_msg)
            elif dst_fpath.exists():
                err_msg = (f'Execute: Deploy aggregated config: Save content:'
                           f' {dst_fpath}: Same-named file already exists!')
                raise cr_exc.SetupCommandError(err_msg)

            try:
                dst_fpath.write_text(rendered_content)
                LOG.debug(f'{self.msg_src}: Execute: Deploy aggregated config:'
                          f' Save content: {dst_fpath}: OK')
            except (OSError, RuntimeError) as e:
                err_msg = (f'Execute: Deploy aggregated config: Save content:'
                           f' {dst_fpath}: {type(e).__name__}: {e}')
                raise cr_exc.SetupCommandError(err_msg) from e

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
        pkg_manifests = (
            self.config.inst_storage.get_pkgactive(PackageManifest.load)
        )
        packages_bulk = {
            m.pkg_id.pkg_name: Package(manifest=m) for m in pkg_manifests
        }

        for package in cr_utl.pkg_sort_by_deps(packages_bulk):
            pkg_id = package.manifest.pkg_id
            mheading = f'{self.msg_src}: Execute: {pkg_id.pkg_name}'

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
