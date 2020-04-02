"""Panda package management for Windows.

Application core constant objects.
"""
from pathlib import Path


# Package's installation config files

PKG_CFG_DNAME = 'conf'

# Package info descriptor file
PKG_INFO_FPATH = 'pkginfo.json'
# Package extra installation options descriptor file
PKG_EXTCFG_FEXT = 'extra'
PKG_EXTCFG_FNAME = '.'.join(['{pkg_name}', PKG_EXTCFG_FEXT, 'j2'])
PKG_EXTCFG_FPATH = str(Path(PKG_CFG_DNAME, PKG_EXTCFG_FNAME))
# Package service options descriptor file
PKG_SVCCFG_FEXT = 'nssm'
PKG_SVCCFG_FNAME = '.'.join(['{pkg_name}', PKG_SVCCFG_FEXT, 'j2'])
PKG_SVCCFG_FPATH = str(Path(PKG_CFG_DNAME, PKG_SVCCFG_FNAME))

# List of package installation config file extensions
PKG_INSTCFG_FEXTS = [PKG_EXTCFG_FEXT, PKG_SVCCFG_FEXT]
