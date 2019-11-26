"""Panda package management for Windows.

DC/OS package extra installation options manager exceptions definition.
"""

from common import exceptions as cm_exc


class InstExtrasManagerError(cm_exc.WinpandaError):
    """Generic DC/OS package installation extra options manager error."""
    pass


class InstExtrasManagerConfigError(InstExtrasManagerError):
    """DC/OS package installation extra options manager configuration error."""
    pass
