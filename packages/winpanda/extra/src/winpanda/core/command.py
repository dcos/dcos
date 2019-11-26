"""Panda package management for Windows.

DC/OS package management command definitions.
"""
import abc

from common import logger
from common.cli import CLI_COMMAND, CLI_CMDTARGET, CLI_CMDOPT
from core import cmdconf
from core import exceptions as cr_exc
from core.package.id import PackageId
from core.package.manifest import PackageManifest
from core.package.package import Package
from core import utils as cr_utl
from extm import exceptions as extm_exc
from svcm import exceptions as svcm_exc
from svcm.nssm import WinSvcManagerNSSM, SVC_STATUS

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
        msg_src = self.__class__.__name__
        super(CmdSetup, self).__init__(**cmd_opts)
        if self.cmd_opts.get(CLI_CMDOPT.CMD_TARGET) == CLI_CMDTARGET.STORAGE:
            # Deactivate cluster-related configuration steps
            self.cmd_opts[CLI_CMDOPT.DCOS_CLUSTERCFGPATH] = 'NOP'

        self.config = cmdconf.create(**self.cmd_opts)
        LOG.debug(f'{msg_src}: cmd_opts: {self.cmd_opts}')

    def verify_cmd_options(self):
        """Verify command options."""
        pass

    def execute(self):
        """Execute command."""
        msg_src = self.__class__.__name__
        LOG.debug(f'{msg_src}: Execute: Target:'
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
            packages_bulk = []
            for item in self.config.ref_pkg_list:
                pkg_id = PackageId(pkg_id=item)

                try:
                    self.config.inst_storage.add_package(
                        pkg_id=pkg_id,
                        dstor_root_url=dstor_root_url,
                        dstor_pkgrepo_path=dstor_pkgrepo_path
                    )
                except cr_exc.RCError as e:
                    err_msg = (f'{msg_src}: Execute: Add package to local'
                               f' repository: {pkg_id.pkg_id}: {e}')
                    raise cr_exc.SetupCommandError(err_msg) from e

                try:
                    package = Package(
                        pkg_id=pkg_id,
                        istor_nodes=self.config.inst_storage.istor_nodes,
                        cluster_conf=self.config.cluster_conf
                    )
                except cr_exc.RCError as e:
                    err_msg = (f'{msg_src}: Execute: Initialize package:'
                               f' {pkg_id.pkg_id}: {e}')
                    raise cr_exc.SetupCommandError(err_msg) from e

                packages_bulk.append(package)

            # Finalize package setup procedures taking package mutual
            # dependencies into account.
            for package in cr_utl.pkg_sort_by_deps(packages_bulk):
                self._handle_pkg_inst_extras(package)
                self._handle_pkg_svc_setup(package)

                try:
                    package.manifest.save()
                except cr_exc.RCError as e:
                    err_msg = (f'{msg_src}: Execute: Register package:'
                               f' {package.manifest.pkg_id.pkg_id}: {e}')
                    raise cr_exc.SetupCommandError(err_msg)

                LOG.info(f'{msg_src}: Setup package:'
                         f' {package.manifest.pkg_id.pkg_id}: OK')

    def _handle_pkg_inst_extras(self, package):
        """Process package extra installation options.

        :param package: Package, DC/OS package manager object
        """
        msg_src = self.__class__.__name__

        LOG.debug(f'{msg_src}: Handle extra install options:'
                  f' ext_manager: {package.ext_manager}')

        if package.ext_manager:
            try:
                package.ext_manager.handle_install_extras()
            except extm_exc.InstExtrasManagerError as e:
                err_msg = (f'Execute: Handle extra install options:'
                           f' {package.manifest.pkg_id.pkg_name}: {e}')
                raise cr_exc.SetupCommandError(err_msg) from e

        LOG.debug(f'{msg_src}: Handle extra install options:'
                  f' {package.manifest.pkg_id.pkg_name}: OK')

    def _handle_pkg_svc_setup(self, package):
        """Execute steps on package service setup.

        :param package: Package, DC/OS package manager object
        """
        msg_src = self.__class__.__name__

        if package.svc_manager:
            try:
                ret_code, stdout, stderr = package.svc_manager.status()
            except svcm_exc.ServiceManagerCommandError as e:
                LOG.debug(f'{msg_src}: Execute: Get initial service status:'
                          f' {package.manifest.pkg_id.pkg_name}: {e}')
                # Try to setup, as a service (expectedly) doesn't exist and
                # checking it's status naturally would yield an error.
                try:
                    package.svc_manager.setup()
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'Execute: Setup service:'
                               f' {package.manifest.pkg_id.pkg_name}: {e}')
                    raise cr_exc.SetupCommandError(err_msg) from e
            else:
                LOG.debug(f'{msg_src}: Execute: Get initial service status:'
                          f' {package.manifest.pkg_id.pkg_name}:'
                          f' stdout[{stdout}] stderr[{stderr}]')
                svc_status = str(stdout).strip().rstrip('\n')
                # Try to remove existing service
                try:
                    if svc_status == SVC_STATUS.RUNNING:
                        package.svc_manager.stop()

                    package.svc_manager.remove()
                    LOG.debug(f'{msg_src}: Execute: Remove existing service:'
                              f' {package.manifest.pkg_id.pkg_name}: OK')
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'Execute: Remove existing service:'
                               f' {package.manifest.pkg_id.pkg_name}: {e}')
                    raise cr_exc.SetupCommandError(err_msg) from e
                # Setup a replacement service
                try:
                    package.svc_manager.setup()
                    ret_code, stdout, stderr = (package.svc_manager.status())
                    svc_status = str(stdout).strip().rstrip('\n')
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'Execute: Setup replacement service:'
                               f' {package.manifest.pkg_id.pkg_name}: {e}')
                    raise cr_exc.SetupCommandError(err_msg) from e
                else:
                    if svc_status != SVC_STATUS.STOPPED:
                        err_msg = (f'Execute: Setup replacement service:'
                                   f' {package.manifest.pkg_id.pkg_name}:'
                                   f' Invalid status: {svc_status}')
                        raise cr_exc.SetupCommandError(err_msg)

            LOG.debug(f'{msg_src}: Setup service:'
                      f' {package.manifest.pkg_id.pkg_name}: OK')


@command_type(CLI_COMMAND.START)
class CmdStart(Command):
    """Start command implementation."""
    def __init__(self, **cmd_opts):
        """Constructor."""
        msg_src = self.__class__.__name__
        super(CmdStart, self).__init__(**cmd_opts)

        self.config = cmdconf.create(**self.cmd_opts)
        LOG.debug(f'{msg_src}: cmd_opts: {self.cmd_opts}')

    def verify_cmd_options(self):
        """Verify command options."""
        pass

    def execute(self):
        """Execute command."""
        msg_src = self.__class__.__name__

        pkg_manifests = (
            self.config.inst_storage.get_pkgactive(PackageManifest.load)
        )
        packages_bulk = [Package(manifest=m) for m in pkg_manifests]

        for package in cr_utl.pkg_sort_by_deps(packages_bulk):
            pkg_id = package.manifest.pkg_id
            LOG.debug(f'{msg_src}: Execute: Package: {package.manifest.body}')

            if package.manifest.pkg_svccfg:
                try:
                    ret_code, stdout, stderr = package.svc_manager.status()
                except svcm_exc.ServiceManagerCommandError as e:
                    err_msg = (f'Execute: Get initial service status:'
                               f' {pkg_id.pkg_name}: {e}')
                    raise cr_exc.StartCommandError(err_msg) from e
                else:
                    LOG.debug(f'{msg_src}: Execute: Get initial service'
                              f' status: {pkg_id.pkg_name}: stdout[{stdout}]'
                              f' stderr[{stderr}]')
                    svc_status = str(stdout).strip().rstrip('\n')

                if svc_status == SVC_STATUS.STOPPED:
                    try:
                        package.svc_manager.start()
                    except svcm_exc.ServiceManagerCommandError as e:
                        err_msg = (f'Execute: Start service:'
                                   f' {pkg_id.pkg_name}: {e}')
                        raise cr_exc.StartCommandError(err_msg) from e

                    try:
                        ret_code, stdout, stderr = package.svc_manager.status()
                        LOG.debug(f'{msg_src}: Execute: Get final service'
                                  f' status: {pkg_id.pkg_name}:'
                                  f' stdout[{stdout}] stderr[{stderr}]')
                        svc_status = str(stdout).strip().rstrip('\n')

                        if svc_status != SVC_STATUS.RUNNING:
                            err_msg = (f'Execute: Service failed to start:'
                                       f' {pkg_id.pkg_name}: {svc_status}')
                            raise cr_exc.StartCommandError(err_msg)
                    except svcm_exc.ServiceManagerCommandError as e:
                        err_msg = (f'Execute: Get final service status:'
                                   f' {pkg_id.pkg_name}: {e}')
                        raise cr_exc.StartCommandError(err_msg) from e
                elif svc_status == SVC_STATUS.RUNNING:
                    LOG.warning(f'{msg_src}: Execute: Service is already'
                                f' running: {pkg_id.pkg_name}')
                else:
                    err_msg = (f'Execute: Invalid service status:'
                               f' {pkg_id.pkg_name}: {svc_status}')
                    raise cr_exc.StartCommandError(err_msg)
