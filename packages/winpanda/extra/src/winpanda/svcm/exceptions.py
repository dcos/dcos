"""Panda package management for Windows.

Windows service management exception definitions.
"""
import configparser as cp

from common import exceptions as cm_exc

# These errors may be thrown by the ConfigParser.get() method.
CONFPARSER_GET_ERRORS = (cp.NoOptionError, cp.InterpolationError)


class ServiceManagerError(cm_exc.WinpandaError):
    """Generic service manager error."""
    pass


class ServiceManagerConfigError(ServiceManagerError):
    """Service manager configuration error."""
    pass


class ServiceManagerSetupError(ServiceManagerError):
    """Service manager setup error."""
    pass


class ServiceManagerCommandError(ServiceManagerError):
    """Service manager command execution error."""
    pass


class ServiceError(cm_exc.WinpandaError):
    """Generic service error."""
    pass


class ServiceConfigError(ServiceError):
    """Service configuration error."""
    pass


class ServiceSetupError(ServiceError):
    """Service setup error."""
    pass


class ServiceWipeError(ServiceError):
    """Service wipe off error."""
    pass


class ServiceStopError(ServiceError):
    """Service stop error."""
    pass


class ServiceTransientError(ServiceError):
    """Service intermittent error."""
    pass


class ServicePersistentError(ServiceError):
    """Service steady error."""
    pass
