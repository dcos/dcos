"""Panda package management for Windows.

DC/OS package management command definitions.
"""
import abc

from common.cli import CLI_COMMAND, CLI_CMDTARGET, CLI_CMDOPT
from common import logger
from core import cmdconf


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
        self.config = cmdconf.create(**self.cmd_opts)
        LOG.debug(f'{self.__class__.__name__}: cmd_opts: {self.cmd_opts}')
        LOG.debug(f'{self.__class__.__name__}: config: inst_storage:'
                  f' construction_plist:'
                  f' {self.config.inst_storage.construction_plist}')

    def verify_cmd_options(self):
        """Verify command options."""
        pass

    def execute(self):
        """Execute command."""
        if self.cmd_opts.get(CLI_CMDOPT.CMD_TARGET) == CLI_CMDTARGET.STORAGE:
            self.config.inst_storage.construct(
                clean=self.cmd_opts.get(CLI_CMDOPT.INST_CLEAN)
            )
        elif self.cmd_opts.get(CLI_CMDOPT.CMD_TARGET) == CLI_CMDTARGET.PKGALL:
            for pkg_meta in self.config.tree_info:
                self.config.packages.get(pkg_meta.get('id')).svc_manager.setup()
                self.config.packages.get(pkg_meta.get('id')).svc_manager.start()
