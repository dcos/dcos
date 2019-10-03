"""Panda package management for Windows (Winpanda).

Exception definitions.
"""


class WinpandaError(Exception):
    """Generic Winpanda error."""
    pass


class InstallationError(WinpandaError):
    """Generic DC/OS installation error."""
    pass


class InstallationConfigError(InstallationError):
    """DC/OS installation configuration error."""
    pass


class CommandError(InstallationError):
    """DC/OS Installation management command error."""
    pass


class SetupCommandError(InstallationError):
    """DC/OS Installation 'setup' management command error."""
    pass
