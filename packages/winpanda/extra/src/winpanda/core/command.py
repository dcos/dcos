"""Panda package management for Windows (Winpanda).

Command definitions.
"""
import abc

from core import logger
from core import cmd_conf


LOG = logger.get_logger(__name__)

CMD_TYPES = {}


def create(**cmd_opts):
    """Instantiate a command.

    :param cmd_opts: dict, command options:
                     {
                         'command_name': <str>
                     }
    """
    command_name = cmd_opts.get('command_name', 'help')

    if command_name.lower() not in CMD_TYPES:
        command_name = 'help'

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


@command_type('help')
class HelpCmd(Command):
    """Help command implementation."""
    def __init__(self, **cmd_opts):
        """"""
        super(HelpCmd, self).__init__(**cmd_opts)
        self.description = '''
            Panda package management for Windows.
        '''

    def verify_cmd_options(self):
        """Verify command options."""
        pass

    def execute(self):
        """Execute command."""
        print(self.description)


@command_type('setup')
class SetupCmd(Command):
    """Setup command implementation."""
    def __init__(self, **cmd_opts):
        """"""
        super(SetupCmd, self).__init__(**cmd_opts)
        self.config = cmd_conf.create(**self.cmd_opts)
        # self.active_packages = self.fetch_active_pkg_list()
        # self.create_pkg_repo()

    def verify_cmd_options(self):
        """Verify command options."""
        pass

    def execute(self):
        """Execute command."""
        print(f'Setup command: cmd_opts: {self.cmd_opts}')
        for pkg_meta in self.config.tree_info:
            self.config.packages.get(pkg_meta.get('id')).svc_manager.setup()
            self.config.packages.get(pkg_meta.get('id')).svc_manager.start()
