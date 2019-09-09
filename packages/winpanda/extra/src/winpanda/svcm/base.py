"""Winpanda: Windows service management: Base manager interface definition.
"""
import abc

SVCM_TYPES = {}


def create(svcm_opts, *args, **kwargs):
    """Instantiate a Windows service manager object.

    :param svcm_opts: dict, Windows service manager specification
    """
    executor = svcm_opts.get('executor')

    return SVCM_TYPES[executor](svcm_opts, *args, **kwargs)


def svcm_type(executor):
    """Register a Windows service manager class in the service manager types
    registry.

    :param executor: str, name of underlying executor tool
    """
    def decorator(cls):
        """"""
        SVCM_TYPES[executor] = cls
        return cls

    return decorator


class WindowsServiceManager(metaclass=abc.ABCMeta):
    """Abstract base class for Windows service manager types.
    """
    def __init__(self, svcm_opts, *args, **kwargs):
        """Constructor.
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
        """Install (register) configuration for a Windows service.
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

    def stop(self, *args, **kwargs):
        """Stop a registered service (immediately).
        """
        pass

    def status(self, *args, **kwargs):
        """Discover status of a registered service.
        """
        pass
