"""Panda package management for Windows.

DC/OS package management command definitions.
"""
import abc

from common import logger
from common.cli import CLI_COMMAND, CLI_CMDTARGET, CLI_CMDOPT
import configparser as cfp
from core import cmdconf
from core.package import PackageId, PackageManifest, Package
from svcm import exceptions as svcm_exc
from svcm.nssm import WinSvcManagerNSSM

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
        super(CmdSetup, self).__init__(**cmd_opts)
        if self.cmd_opts.get(CLI_CMDOPT.CMD_TARGET) == CLI_CMDTARGET.STORAGE:
            # Deactivate cluster-related configuration steps
            self.cmd_opts[CLI_CMDOPT.DCOS_CLUSTERCFGPATH] = 'NOP'

        self.config = cmdconf.create(**self.cmd_opts)
        LOG.debug(f'{self.__class__.__name__}: cmd_opts: {self.cmd_opts}')

    def verify_cmd_options(self):
        """Verify command options."""
        pass

    def execute(self):
        """Execute command."""
        if self.cmd_opts.get(CLI_CMDOPT.CMD_TARGET) == CLI_CMDTARGET.STORAGE:
            LOG.debug(f'{self.__class__.__name__}:'
                      f' cmd_target: {CLI_CMDTARGET.STORAGE}')
            self.config.inst_storage.construct(
                clean=self.cmd_opts.get(CLI_CMDOPT.INST_CLEAN)
            )
        elif self.cmd_opts.get(CLI_CMDOPT.CMD_TARGET) == CLI_CMDTARGET.PKGALL:
            LOG.debug(f'{self.__class__.__name__}:'
                      f' cmd_target: {CLI_CMDTARGET.PKGALL}')
            # Add packages to the local package repository
            dstor_root_url = self.config.cluster_conf.get(
                'distribution-storage', {}
            ).get('rooturl', '')
            dstor_pkgrepo_path = self.config.cluster_conf.get(
                'distribution-storage', {}
            ).get('pkgrepopath', '')

            for item in self.config.ref_pkg_list:
                pkg_id = PackageId(pkg_id=item)
                self.config.inst_storage.add_package(
                    pkg_id=pkg_id,
                    dstor_root_url=dstor_root_url,
                    dstor_pkgrepo_path=dstor_pkgrepo_path
                )
                package = Package(
                    pkg_id=pkg_id,
                    pkgrepo_dpath=self.config.inst_storage.pkgrepo_dpath,
                    pkgactive_dpath=self.config.inst_storage.pkgactive_dpath,
                    cluster_conf=self.config.cluster_conf
                )

                try:
                    ret_code, stdout, stderr = package.svc_manager.status()
                except svcm_exc.ServiceManagerCommandError as e:
                    LOG.debug(f'{self.__class__.__name__}: svc_status: {e}')
                    package.svc_manager.setup()
                else:
                    LOG.debug(f'{self.__class__.__name__}: svc_status:'
                              f' ret_code[{ret_code}] stdout[{stdout}]'
                              f' stderr[{stderr}]')
                    if stdout == 'SERVICE_RUNNING':
                        package.svc_manager.stop()
                        ret_code, stdout, stderr = package.svc_manager.status()
                        LOG.debug(f'{self.__class__.__name__}: Stop service'
                                  f'svc_status: ret_code[{ret_code}]'
                                  f' stdout[{stdout}] stderr[{stderr}]')

                    package.svc_manager.remove()
                    try:
                        ret_code, stdout, stderr = package.svc_manager.status()
                    except svcm_exc.ServiceManagerCommandError as e:
                        LOG.debug(f'{self.__class__.__name__}: svc_status: {e}')
                    else:
                        LOG.debug(f'{self.__class__.__name__}: Remove service:'
                                  f' svc_status: ret_code[{ret_code}]'
                                  f' stdout[{stdout}] stderr[{stderr}]')

                    package.svc_manager.setup()
                    ret_code, stdout, stderr = package.svc_manager.status()
                    LOG.debug(f'{self.__class__.__name__}: Setup service:'
                              f' svc_status: ret_code[{ret_code}]'
                              f' stdout[{stdout}] stderr[{stderr}]')

                package.manifest.save()


@command_type(CLI_COMMAND.START)
class CmdStart(Command):
    """Start command implementation."""
    def __init__(self, **cmd_opts):
        """"""
        super(CmdStart, self).__init__(**cmd_opts)

        self.config = cmdconf.create(**self.cmd_opts)
        LOG.debug(f'{self.__class__.__name__}: cmd_opts: {self.cmd_opts}')

    def verify_cmd_options(self):
        """Verify command options."""
        pass

    def execute(self):
        """Execute command."""
        for pkg_manifest in self.config.inst_storage.get_pkgactive():
            svc_conf = cfp.ConfigParser()
            svc_conf.read_dict(pkg_manifest.svc_conf)
            cluster_conf = cfp.ConfigParser()
            cluster_conf.read_dict(self.config.cluster_conf)
            svc_manager = WinSvcManagerNSSM(
                svc_conf=svc_conf, cluster_conf=cluster_conf
            )

            try:
                ret_code, stdout, stderr = svc_manager.status()
                LOG.debug(
                    f'{self.__class__.__name__}: Service status:'
                    f' ret_code[{ret_code}] stdout[{stdout}] stderr[{stderr}]'
                )
            except svcm_exc.ServiceManagerCommandError as e:
                LOG.error(f'{self.__class__.__name__}: Service status: {e}')
                continue

            if stdout == 'SERVICE_STOPPED':
                try:
                    svc_manager.start()
                    ret_code, stdout, stderr = svc_manager.status()
                    LOG.debug(
                        f'{self.__class__.__name__}: Service status:'
                        f' svc_status: ret_code[{ret_code}] stdout[{stdout}]'
                        f' stderr[{stderr}]'
                    )
                except svcm_exc.ServiceManagerCommandError as e:
                    LOG.error(f'{self.__class__.__name__}: Service status: {e}')
                    continue
            else:
                LOG.error(f'{self.__class__.__name__}: Service status:'
                          f' svc_status: ret_code[{ret_code}]'
                          f' stdout[{stdout}] stderr[{stderr}]')
