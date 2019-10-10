"""Panda package management for Windows.

DC/OS installation local storage management tools.

Default local storage layout for DC/OS installation:

<inst_drive>:/                # DC/OS installation drive
    +-<inst_root>/            # DC/OS installation root dir
        +-<inst_cfg>/         # DC/OS installation config dir
        +-<inst_pkgrepo>/     # DC/OS local package repository dir
        +-<inst_state>/       # DC/OS installation state dir
            +-<pkgactive>/    # DC/OS active packages index
        +-<inst_var>/         # DC/OS installation variable data root dir
            +-<inst_work>/    # Package-specific work dirs
            +-<inst_run>/     # Package-specific/common runtime data
            +-<inst_log>/     # Package-specific/common log files
            +-<inst_tmp>/     # Package-specific/common temporary data
"""
import json
from pathlib import Path

from common import logger
from common import utils as cm_utl
from core import exceptions as cr_exc


LOG = logger.get_logger(__name__)

# DC/OS installation drive
DCOS_INST_DRIVE_DFT = 'c:'

# DC/OS installation root directory path
DCOS_INST_ROOT_DPATH_DFT = 'dcos'

# >>>>>
# DC/OS installation configuration root directory
DCOS_INST_CFG_DPATH_DFT = 'conf'
# DC/OS cluster configuration file
DCOS_CLUSTERCFG_FNAME_DFT = 'cluster.conf'

# >>>>>
# DC/OS local package repository root directory
DCOS_INST_PKGREPO_DPATH_DFT = 'packages'

# >>>>>
# DC/OS installation state directory
DCOS_INST_STATE_DPATH_DFT = 'state'
# DC/OS active packages index directory
DCOS_PKGACTIVE_DPATH_DFT = 'pkgactive'

# >>>>>
# DC/OS installation variable data root directory
DCOS_INST_VAR_DPATH_DFT = 'var'
# Package-specific/common log files
DCOS_INST_LOG_DPATH_DFT = 'log'
# Package-specific work dirs
DCOS_INST_WORK_DPATH_DFT = 'opt'
# Package-specific runtime data
DCOS_INST_RUN_DPATH_DFT = 'run'
# Package-specific/common temporary data
DCOS_INST_TMP_DPATH_DFT = 'tmp'


class InstallationStorage:
    """"""
    def __init__(self,
                 drive=DCOS_INST_DRIVE_DFT,
                 root_dpath=DCOS_INST_ROOT_DPATH_DFT,
                 cfg_dpath=DCOS_INST_CFG_DPATH_DFT,
                 pkgrepo_dpath=DCOS_INST_PKGREPO_DPATH_DFT,
                 state_dpath=DCOS_INST_STATE_DPATH_DFT,
                 pkgactive_dpath=DCOS_PKGACTIVE_DPATH_DFT,
                 var_dpath=DCOS_INST_VAR_DPATH_DFT,
                 work_dpath=DCOS_INST_WORK_DPATH_DFT,
                 run_dpath=DCOS_INST_RUN_DPATH_DFT,
                 log_dpath=DCOS_INST_LOG_DPATH_DFT,
                 tmp_dpath=DCOS_INST_TMP_DPATH_DFT):
        """DC/OS installation FS layout manager.

        :param drive:           str, DC/OS installation drive spec (ex. 'c:')
        :param root_dpath:      str, DC/OS installation root dir path
        :param cfg_dpath:       str, DC/OS installation configs root dir path
        :param pkgrepo_dpath:   str, local package repository root dir path
        :param state_dpath:     str, DC/OS installation state root dir path
        :param pkgactive_dpath: str, DC/OS active packages index dir path
        :param var_dpath:       str, DC/OS installation variable data root
                                dir path
        :param work_dpath:      str, package-specific work dirs root dir path
        :param run_dpath:       str, package-specific runtime data dirs root
                                dir path
        :param log_dpath:       str, package-specific/common log files root
                                dir path
        :param tmp_dpath:       str, package-specific/common temporary data
                                root dir path
        """
        # Refine/verify drive specification
        drive_ = Path(f'{drive.strip(":")}:').drive
        LOG.debug(f'InstallationStorage: drive_: {drive_}')
        if drive_:
            self.drive = Path(drive_, '/')
        else:
            raise cr_exc.InstallationStorageError(
                f'Invalid drive specification: {drive}'
            )
        # Construct DC/OS installation root dir path
        root_dpath_ = Path(str(root_dpath))
        self.root_dpath = (root_dpath_ if root_dpath_.is_absolute() else
                           Path(self.drive).joinpath(root_dpath_))
        # Construct DC/OS installation configuration dir path
        cfg_dpath_ = Path(str(cfg_dpath))
        self.cfg_dpath = (cfg_dpath_ if cfg_dpath_.is_absolute() else
                          self.root_dpath.joinpath(cfg_dpath_))
        # Construct DC/OS installation local package repository dir path
        pkgrepo_dpath_ = Path(str(pkgrepo_dpath))
        self.pkgrepo_dpath = (
            pkgrepo_dpath_ if pkgrepo_dpath_.is_absolute() else
            self.root_dpath.joinpath(pkgrepo_dpath_)
        )
        # Construct DC/OS installation state dir path
        state_dpath_ = Path(str(state_dpath))
        self.state_dpath = (state_dpath_ if state_dpath_.is_absolute() else
                            self.root_dpath.joinpath(state_dpath_))
        # Construct DC/OS installation active packages index dir path
        pkgactive_dpath_ = Path(str(pkgactive_dpath))
        self.pkgactive_dpath = (
            pkgactive_dpath_ if pkgactive_dpath_.is_absolute() else
            self.state_dpath.joinpath(pkgactive_dpath_)
        )
        # Construct DC/OS installation variable data root dir path
        var_dpath_ = Path(str(var_dpath))
        self.var_dpath = (var_dpath_ if var_dpath_.is_absolute() else
                          self.root_dpath.joinpath(var_dpath_))
        # Construct DC/OS installation package-specific work dirs root dir path
        work_dpath_ = Path(str(work_dpath))
        self.work_dpath = (work_dpath_ if work_dpath_.is_absolute() else
                           self.var_dpath.joinpath(work_dpath_))
        # Construct DC/OS installation runtime data root dir path
        run_dpath_ = Path(str(run_dpath))
        self.run_dpath = (run_dpath_ if run_dpath_.is_absolute() else
                          self.var_dpath.joinpath(run_dpath_))
        # Construct DC/OS installation logging data root dir path
        log_dpath_ = Path(str(log_dpath))
        self.log_dpath = (log_dpath_ if log_dpath_.is_absolute() else
                          self.var_dpath.joinpath(log_dpath_))
        # Construct DC/OS installation temporary data root dir path
        tmp_dpath_ = Path(str(tmp_dpath))
        self.tmp_dpath = (tmp_dpath_ if tmp_dpath_.is_absolute() else
                          self.var_dpath.joinpath(tmp_dpath_))

        self.construction_plist = (
            self.root_dpath,
            self.cfg_dpath,
            self.pkgrepo_dpath,
            self.state_dpath,
            self.pkgactive_dpath,
            self.var_dpath,
            self.work_dpath,
            self.run_dpath,
            self.log_dpath,
            self.tmp_dpath
        )

    def collect_pkgactive(self):
        """Create a list of active packages."""
        active_packages = []

        for path in self.pkgactive_dpath.iterdir():
            try:
                with path.open() as fp:
                    pkg_manifest = json.load(fp=fp)
            except (OSError, RuntimeError) as e:
                raise cr_exc.InstallationStorageError(
                    f'Collect active packages: {path}: {type(e).__name__}: {e}'
                )

            active_packages.append(pkg_manifest.get('pkg_id'))

        return active_packages

    def construct(self, clean=False):
        """Construct DC/OS installation storage.

        :param clean: boolean, create a clean FS folder structure, wiping
                      out any possible leftovers, if True. Otherwise repair FS
                      directory structure, creating any missed pieces, as
                      required.
        """
        for path in self.construction_plist:
            if path.exists():
                if path.is_symlink():
                    raise cr_exc.InstallationStorageError(
                        f'Construction: Symlink conflict: {path}'
                    )
                elif path.is_reserved():
                    raise cr_exc.InstallationStorageError(
                        f'Construction: Reserved name conflict: {path}'
                    )
                elif not path.is_dir():
                    # Remove a file
                    try:
                        path.unlink()
                    except (OSError, RuntimeError) as e:
                        raise cr_exc.InstallationStorageError(
                            f'Construction: Cleanup failure: {path}:'
                            f' {type(e).__name__}: {e}'
                        )
                elif clean is True:
                    # Remove an existing DC/OS installation storage element
                    try:
                        cm_utl.rmdir(path=path, recursive=True)
                    except (OSError, RuntimeError) as e:
                        raise cr_exc.InstallationStorageError(
                            f'Construction: Cleanup failure: {path}:'
                            f' {type(e).__name__}: {e}'
                        )
                    # Create a fresh DC/OS installation storage element
                    try:
                        path.mkdir(parents=True, exist_ok=True)
                    except (OSError, RuntimeError) as e:
                        raise cr_exc.InstallationStorageError(
                            f'Construction: Create element: {path}:'
                            f' {type(e).__name__}: {e}'
                        )
            else:
                # Create a fresh DC/OS installation storage element
                try:
                    path.mkdir(parents=True, exist_ok=True)
                except (OSError, RuntimeError) as e:
                    raise cr_exc.InstallationStorageError(
                        f'Construction: Create element: {path}:'
                        f' {type(e).__name__}: {e}'
                    )

    def destruct(self):
        """Remove entire existing DC/OS installation storage."""
        for path in self.construction_plist:
            if path.is_absolute() and path.is_dir():
                try:
                    cm_utl.rmdir(path=path, recursive=True)
                except (OSError, RuntimeError) as e:
                    raise cr_exc.InstallationStorageError(
                        f'Destruction: {path}: {type(e).__name__}: {e}'
                    )
