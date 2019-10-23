"""Panda package management for Windows.

Base Windows service manager interface definition.
"""
import abc

from common import logger
from svcm import exceptions as svcm_exc


LOG = logger.get_logger(__name__)

SVCM_TYPES = {}


def create(**svcm_opts):
    """Instantiate a Windows service manager.

    :param svcm_opts: dict, Windows service manager options:
                      {
                          'executor_name': <str>,
                          'exec_path': <pathlib.Path>
                      }
    """
    executor_name = svcm_opts.get('executor_name')

    err_msg = None
    if executor_name is None:
        err_msg = ('Internal Error: Windows service manager:'
                   ' Executor name not specified')
    elif executor_name not in SVCM_TYPES:
        err_msg = ('Internal Error: Windows service manager: '
                   f'Not supported: {executor_name}')

    if err_msg is not None:
        LOG.critical(err_msg)
        raise svcm_exc.ServiceManagerConfigError(err_msg)

    return SVCM_TYPES[executor_name](**svcm_opts)


def svcm_type(executor_name):
    """Register a Windows service manager class in the service manager types
    registry.

    :param executor_name: str, name of underlying executor tool
    """
    def decorator(cls):
        """"""
        SVCM_TYPES[executor_name] = cls
        return cls

    return decorator


class WindowsServiceManager(metaclass=abc.ABCMeta):
    """Abstract base class for Windows service manager types.
    """
    def __init__(self, **svcm_opts):
        """Constructor.

        :param svcm_opts: dict, service manager options:
                          {
                              'executor_name': <str>,
                              'exec_path': <pathlib.Path>
                          }
        """
        self.svcm_opts = svcm_opts

    def __repr__(self):
        return (
            '<%s(svcm_opts="%s")>' % (self.__class__.__name__, self.svcm_opts)
        )

    def __str__(self):
        return self.__repr__()

    @abc.abstractmethod
    def verify_svcm_options(self, *args, **kwargs):
        """Verify Windows service manager options.
        """
        pass

    @abc.abstractmethod
    def setup(self, *args, **kwargs):
        """Setup (register) configuration for a Windows service.
        """
        pass

    @abc.abstractmethod
    def remove(self, *args, **kwargs):
        """Uninstall configuration for a Windows service.
        """
        pass

    @abc.abstractmethod
    def enable(self, *args, **kwargs):
        """Turn service's  auto-start flag on (start service at OS bootstrap).
        """
        pass

    @abc.abstractmethod
    def disable(self, *args, **kwargs):
        """Turn service's  auto-start flag off (do not start service at OS
        bootstrap).
        """
        pass

    @abc.abstractmethod
    def start(self, *args, **kwargs):
        """Start a registered service (immediately).
        """
        pass

    @abc.abstractmethod
    def stop(self, *args, **kwargs):
        """Stop a registered service (immediately).
        """
        pass

    @abc.abstractmethod
    def restart(self, *args, **kwargs):
        """Restart   a registered service (immediately).
        """
        pass

    @abc.abstractmethod
    def status(self, *args, **kwargs):
        """Discover status of a registered service.
        """
        pass
