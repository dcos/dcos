"""Panda package management for Windows.

Core exception definitions.
"""
from common import exceptions as cm_exc
from common.exceptions import JSON_ERRORS


class InstallationConfigError(cm_exc.InstallationError):
    """DC/OS installation configuration error."""
    pass


class InstallationStorageError(cm_exc.InstallationError):
    """DC/OS installation FS layout error."""
    pass


class RCError(cm_exc.InstallationError):
    """Generic local resource error."""
    pass


class RCNotFoundError(RCError):
    """Local resource does not exist."""
    pass


class RCDownloadError(RCError):
    """Resource download error.
    """


class RCExtractError(RCError):
    """Resource extraction/unpacking error.
    """


class RCCreateError(RCError):
    """Resource creation error.
    """


class RCRemoveError(RCError):
    """Resource removal error.
    """


class RCInvalidError(RCError):
    """Resource doesn't conform expected requirements.
    """


class RCElementError(RCError):
    """Resource's element doesn't conform imposed requirements.
    """


class CommandError(cm_exc.InstallationError):
    """DC/OS Installation management command error."""
    pass


class SetupCommandError(cm_exc.InstallationError):
    """DC/OS Installation 'setup' management command error."""
    pass


class StartCommandError(cm_exc.InstallationError):
    """DC/OS Installation 'start' management command error."""
    pass
