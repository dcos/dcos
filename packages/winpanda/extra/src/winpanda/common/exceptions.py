"""Panda package management for Windows.

Exception definitions.
"""
import json

JSON_ERRORS = (TypeError, ValueError, json.JSONDecodeError)


class WinpandaError(Exception):
    """Generic Winpanda error."""
    pass


class InstallationError(WinpandaError):
    """Generic DC/OS installation error."""
    pass


class ExternalCommandError(WinpandaError):
    """External command execution error."""
    pass
