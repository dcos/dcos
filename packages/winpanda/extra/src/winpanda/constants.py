"""Panda package management for Windows (Winpanda).

Application-wide constant objects.
"""
from pathlib import Path

# Default local FS layout for DC/OS installation

# DC/OS installation root directory
DCOS_INST_ROOT_DPATH_DFT = Path('c:/dcos')

# DC/OS installation configuration root directory
DCOS_CFG_ROOT_DNAME_DFT = 'conf'
DCOS_CFG_ROOT_DPATH_DFT = DCOS_INST_ROOT_DPATH_DFT.joinpath(
    DCOS_CFG_ROOT_DNAME_DFT
)

# DC/OS cluster configuration file
DCOS_CLUSTERCFG_FNAME_DFT = 'cluster.conf'
DCOS_CLUSTERCFG_FPATH_DFT = DCOS_CFG_ROOT_DPATH_DFT.joinpath(
    DCOS_CLUSTERCFG_FNAME_DFT
)

# DC/OS local package repository root directory
DCOS_PKGREPO_ROOT_DNAME_DFT = 'packages'
DCOS_PKGREPO_ROOT_DPATH_DFT = DCOS_INST_ROOT_DPATH_DFT.joinpath(
    DCOS_PKGREPO_ROOT_DNAME_DFT
)

# DC/OS installation state directory
DCOS_STATE_ROOT_DNAME_DFT = 'active'
DCOS_STATE_ROOT_DPATH_DFT = DCOS_INST_ROOT_DPATH_DFT.joinpath(
    DCOS_STATE_ROOT_DNAME_DFT
)

# DC/OS distribution storage URL
DCOS_DSTOR_URL_DFT = 'https://wintesting.s3.amazonaws.com'

# DC/OS distribution storage package repository path
DCOS_DSTOR_PKGREPO_PATH_DFT = 'testing/packages'


