"""Panda package management for Windows.

Base Windows service manager interface definition.
"""
import abc

from common import logger
from svcm import exceptions as svcm_exc
from typing import Dict, Callable, Any, Tuple

LOG = logger.get_logger(__name__)

SVCM_TYPES = {}  # type: Dict


def create(**svcm_opts: Dict) -> Any:
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


def svcm_type(executor_name: str) -> Callable:
    """Register a Windows service manager class in the service manager types
    registry.

    :param executor_name: str, name of underlying executor tool
    """
    def decorator(cls: Any) -> Any:
        """"""
        SVCM_TYPES[executor_name] = cls
        return cls

    return decorator


class WindowsServiceManager(metaclass=abc.ABCMeta):
    """Abstract base class for Windows service manager types.
    """
    def __init__(self, **svcm_opts: Dict):
        """Constructor.

        :param svcm_opts: dict, service manager options:
                          {
                              'executor_name': <str>,
                              'exec_path': <pathlib.Path>
                          }
        """
        self.svcm_opts = svcm_opts

    def __repr__(self) -> str:
        return (
            '<%s(svcm_opts="%s")>' % (self.__class__.__name__, self.svcm_opts)
        )

    def __str__(self) -> str:
        return self.__repr__()

    @abc.abstractmethod
    def verify_svcm_options(self, *args: Any, **kwargs: Any) -> Any:
        """Verify Windows service manager options.
        """
        pass

    @abc.abstractmethod
    def setup(self) -> None:
        """Setup (register) configuration for a Windows service.
        """
        pass

    @abc.abstractmethod
    def remove(self) -> None:
        """Uninstall configuration for a Windows service.
        """
        pass

    @abc.abstractmethod
    def enable(self) -> None:
        """Turn service's  auto-start flag on (start service at OS bootstrap).
        """
        pass

    @abc.abstractmethod
    def disable(self) -> None:
        """Turn service's  auto-start flag off (do not start service at OS
        bootstrap).
        """
        pass

    @abc.abstractmethod
    def start(self) -> None:
        """Start a registered service (immediately).
        """
        pass

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop a registered service (immediately).
        """
        pass

    @abc.abstractmethod
    def restart(self) -> None:
        """Restart   a registered service (immediately).
        """
        pass

    @abc.abstractmethod
    def status(self) -> Tuple:
        """Discover status of a registered service.
        """
        pass
