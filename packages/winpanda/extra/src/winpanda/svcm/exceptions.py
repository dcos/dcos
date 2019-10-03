"""Winpanda: Windows service management.

Exception definitions.
"""
import configparser as cp

import exceptions as exc

# These errors may be thrown by the ConfigParser.get() method.
CONFPARSER_GET_ERRORS = (cp.NoOptionError, cp.InterpolationError)


class ServiceManagerError(exc.WinpandaError):
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


class ServiceError(exc.WinpandaError):
    """Generic service error."""
    pass


class ServiceConfigError(ServiceManagerError):
    """Service configuration error."""
    pass


class ServiceSetupError(ServiceError):
    """Service setup error."""
    pass
