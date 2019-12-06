"""Panda package management for Windows.

DC/OS package configuration files manager exceptions definition.
"""

from common import exceptions as cm_exc
from core import exceptions as cr_exc


class PkgConfManagerError(cm_exc.WinpandaError):
    """Generic DC/OS package configuration files manager error."""
    pass


class PkgConfError(cr_exc.RCError, PkgConfManagerError):
    """Generic DC/OS package configuration source error."""
    pass


class PkgConfNotFoundError(PkgConfError):
    """DC/OS package configuration source directory not found."""
    pass


class PkgConfInvalidError(PkgConfError):
    """Invalid reference or structure of a DC/OS package configuration source
    directory."""
    pass


class PkgConfFileNotFoundError(PkgConfError):
    """DC/OS package configuration source file not found."""
    pass


class PkgConfFileInvalidError(PkgConfError):
    """Invalid reference or structure of a DC/OS package configuration source
    file."""
    pass

