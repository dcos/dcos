"""Panda package management for Windows.

Command configuration object definitions.
"""
import abc
import os
import os.path
import posixpath
import shutil


from common import cli
from common import storage
from common import logger
from core import exceptions as cr_exc
from core.package import Package
from common import utils as cm_utl


LOG = logger.get_logger(__name__)

CMDCONF_TYPES = {}


def create(**cmd_opts):
    """Create configuration for a command.

    :param cmd_opts: dict, command options:
                     {
                         'command_name': <str>,

                     }
    """
    command_name = cmd_opts.get(cli.CLI_CMDOPT.CMD_NAME, '')

    return CMDCONF_TYPES[command_name](**cmd_opts)


def cmdconf_type(command_name):
    """Register a command configuration class in the config types registry.

    :param command_name: str, name of a command
    """
    def decorator(cls):
        """"""
        CMDCONF_TYPES[command_name] = cls
        return cls

    return decorator


class CommandConfig(metaclass=abc.ABCMeta):
    """Abstract base class for command configuration types.
    """
    def __init__(self, **cmd_opts):
        """Constructor."""
        self.cmd_opts = cmd_opts
        # self.cluster_conf = None

    def __repr__(self):
        return (
            '<%s(cmd_opts="%s")>' % (self.__class__.__name__, self.cmd_opts)
        )

    def __str__(self):
        return self.__repr__()


@cmdconf_type(cli.CLI_COMMAND.SETUP)
class CmdConfigSetup(CommandConfig):
    """Configuration for the 'setup' command."""
    def __init__(self, **cmd_opts):
        """"""
        super(CmdConfigSetup, self).__init__(**cmd_opts)
        self.inst_storage = storage.InstallationStorage(
            root_dpath=cmd_opts.get(cli.CLI_CMDOPT.INST_ROOT),
            cfg_dpath=cmd_opts.get(cli.CLI_CMDOPT.INST_CONF),
            pkgrepo_dpath=cmd_opts.get(cli.CLI_CMDOPT.INST_PKGREPO),
            state_dpath=cmd_opts.get(cli.CLI_CMDOPT.INST_STATE),
            var_dpath=cmd_opts.get(cli.CLI_CMDOPT.INST_VAR)
        )
        self.cluster_conf = self.get_cluster_conf()
        self.active_packages = self.fetch_active_pkg_list()

        self.packages = self.create_pkg_repo()  # dict
        self.tree_info = self.active_packages

    def get_cluster_conf(self):
        """"Get a collection of DC/OS cluster configuration options.

        :return: dict, set of DC/OS cluster parameters.
        """
        return {
            'dstor_url': self.cmd_opts.get('dstor_url'),
            'dstor_pkgrepo_path': self.cmd_opts.get('dstor_pkgrepo_path'),
            'master_priv_ipaddr': self.cmd_opts.get('master-priv-ipaddr'),
            'local-priv-ipaddr': self.cmd_opts.get('local-priv-ipaddr')
        }

    @staticmethod
    def fetch_active_pkg_list():
        """Fetch a current list of active packages."""
        active_packages = [
            {'name': 'mesos', 'id': 'mesos--1'},
            {'name': 'dcos-diagnostics', 'id': 'dcos-diagnostics--1'}
        ]

        return active_packages

    def get_pkg_url(self, pkg):
        """"""
        pkg_url = '.'.join([
            posixpath.join(self.cluster_conf.get('dstor_url'),
                           self.cluster_conf.get('dstor_pkgrepo_path'),
                           pkg.get('name'), pkg.get('id')),
            'tar.xz'
        ])

        return pkg_url

    def create_pkg_repo(self):
        """Execute command."""
        pkg_managers = {}

        for pkg in self.active_packages:
            try:
                # Fetch and unpack a package
                cm_utl.download(self.get_pkg_url(pkg=pkg),
                                self.cmd_opts.get('inst_state_path'))
                cm_utl.unpack(
                    '.'.join([
                        os.path.join(self.cmd_opts.get('inst_state_path'),
                                     pkg.get('id')),
                        'tar.xz']),
                    self.cmd_opts.get('inst_pkgrepo_path')
                )
                # Create package manager for a package
                pkg_managers[pkg.get('id')] = Package(pkg.get('id'),
                                                      self.cluster_conf)

                # Workaround for dcos-diagnostics to be able to start
                dst_dpath = self.cmd_opts.get('inst_root_path')
                if pkg.get('name') == 'dcos-diagnostics':
                    # Move binary and config-files to DC/OD installation root.
                    src_dpath = os.path.join(
                        self.cmd_opts.get('inst_pkgrepo_path'),
                        pkg.get('id'), 'bin'
                    )
                    pkg_bin_dpath, pkg_bin_subdirs, pkg_bin_files = next(
                        os.walk(src_dpath)
                    )
                    for src_fname in pkg_bin_files:
                        shutil.copy(os.path.join(pkg_bin_dpath, src_fname),
                                    dst_dpath)
                    # Create a folder for logs
                    log_dpath = os.path.join(dst_dpath, 'mesos-logs')
                    os.mkdir(log_dpath)
            except Exception as e:
                raise cr_exc.SetupCommandError(f'{type(e).__name__}: {e}')

        return pkg_managers
