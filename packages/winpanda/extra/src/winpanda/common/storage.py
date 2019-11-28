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
        +-<inst_bin>/         # DC/OS installation shared executables dir
        +-<inst_lib>/         # DC/OS installation shared libraries dir
"""
# This is how the default DC/OS installation FS layout looks like
# C:/                         # DC/OS installation drive
#   +-dcos/                   # DC/OS installation root dir
#     +-conf/                 # DC/OS installation config dir
#     +-packages/             # DC/OS local package repository dir
#     +-state/                # DC/OS installation state dir
#       +-pkgactive/          # DC/OS active packages index
#     +-var/                  # DC/OS installation variable data root dir
#       +-opt/                # Package-specific work dirs
#       +-run/                # Package-specific/common runtime data
#       +-log/                # Package-specific/common log files
#       +-tmp/                # Package-specific/common temporary data
#     +-bin/                  # DC/OS installation shared executables dir
#     +-lib/                  # DC/OS installation shared libraries dir


from collections import namedtuple
from pathlib import Path
import posixpath
import shutil
import tempfile as tf

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

# >>>>>
# DC/OS installation shared executables root directory
DCOS_INST_BIN_DPATH_DFT = 'bin'

# >>>>>
# DC/OS installation shared libraries root directory
DCOS_INST_LIB_DPATH_DFT = 'lib'


class ISTOR_NODE:
    """DC/OS installation storage core node."""
    DRIVE = 'inst_drive'
    ROOT = 'inst_root'
    CFG = 'inst_cfg'
    PKGREPO = 'inst_pkgrepo'
    STATE = 'inst_state'
    PKGACTIVE = 'pkgactive'
    VAR = 'inst_var'
    WORK = 'inst_work'
    RUN = 'inst_run'
    LOG = 'inst_log'
    TMP = 'inst_tmp'
    BIN = 'inst_bin'
    LIB = 'inst_lib'


IStorNodes = namedtuple('IStorNodes', [
    ISTOR_NODE.DRIVE, ISTOR_NODE.ROOT, ISTOR_NODE.CFG, ISTOR_NODE.PKGREPO,
    ISTOR_NODE.STATE, ISTOR_NODE.PKGACTIVE, ISTOR_NODE.VAR, ISTOR_NODE.WORK,
    ISTOR_NODE.RUN, ISTOR_NODE.LOG, ISTOR_NODE.TMP, ISTOR_NODE.BIN,
    ISTOR_NODE.LIB
])


class InstallationStorage:
    """DC/OS installation storage manager."""
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
                 tmp_dpath=DCOS_INST_TMP_DPATH_DFT,
                 bin_dpath=DCOS_INST_BIN_DPATH_DFT,
                 lib_dpath=DCOS_INST_LIB_DPATH_DFT):
        """Constructor.

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
        :param bin_dpath:       str, shared executables root dir path
        :param lib_dpath:       str, shared libraries root dir path
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
        # Construct DC/OS installation shared executables dir path
        bin_dpath_ = Path(str(bin_dpath))
        self.bin_dpath = (bin_dpath_ if bin_dpath_.is_absolute() else
                          self.root_dpath.joinpath(bin_dpath_))
        # Construct DC/OS installation shared libraries dir path
        lib_dpath_ = Path(str(lib_dpath))
        self.lib_dpath = (lib_dpath_ if lib_dpath_.is_absolute() else
                          self.root_dpath.joinpath(lib_dpath_))

        self.istor_nodes = IStorNodes(**{
            ISTOR_NODE.DRIVE: self.drive,
            ISTOR_NODE.ROOT: self.root_dpath,
            ISTOR_NODE.CFG: self.cfg_dpath,
            ISTOR_NODE.PKGREPO: self.pkgrepo_dpath,
            ISTOR_NODE.STATE: self.state_dpath,
            ISTOR_NODE.PKGACTIVE: self.pkgactive_dpath,
            ISTOR_NODE.VAR: self.var_dpath,
            ISTOR_NODE.WORK: self.work_dpath,
            ISTOR_NODE.RUN: self.run_dpath,
            ISTOR_NODE.LOG: self.log_dpath,
            ISTOR_NODE.TMP: self.tmp_dpath,
            ISTOR_NODE.BIN: self.bin_dpath,
            ISTOR_NODE.LIB: self.lib_dpath,
        })

    def _inst_stor_is_clean_ready(self, clean=False):
        """Check if the DC/OS installation storage may be safely (re-)created
        from the scratch, cleaning up any leftovers from the previous
        installation storage instances.

        :param clean_opt: bool, DC/OS installation storage 'cleanup' flag
        :return:
        """
        # TODO: Implement logic for discovering cleanup readiness.
        return clean

    def construct(self, clean=False):
        """Construct DC/OS installation storage.

        :param clean: boolean, create a clean FS folder structure, wiping
                      out any possible leftovers, if True. Otherwise repair FS
                      directory structure, creating any missed pieces, as
                      required.
        """
        clean_ready = self._inst_stor_is_clean_ready(clean=clean)
        LOG.debug(f'{self.__class__.__name__}:'
                  f' Construction: Clean ready: {clean_ready}')
        rollback_path_list = []

        def rollback():
            """"""
            for path in rollback_path_list:
                # Remove an existing DC/OS installation storage element
                try:
                    cm_utl.rmdir(path=path, recursive=True)
                except (OSError, RuntimeError) as e:
                    LOG.error(f'{self.__class__.__name__}: Construction:'
                              f' Rollback: {path}: {type(e).__name__}: {e}')

        for path in self.istor_nodes[1:]:
            if path.exists():
                if path.is_symlink():
                    rollback()
                    raise cr_exc.InstallationStorageError(
                        f'Construction: Symlink conflict: {path}'
                    )
                elif path.is_reserved():
                    rollback()
                    raise cr_exc.InstallationStorageError(
                        f'Construction: Reserved name conflict: {path}'
                    )
                elif not path.is_dir():
                    # Remove a file
                    try:
                        path.unlink()
                        LOG.debug(f'{self.__class__.__name__}:'
                                  f' Construction: Auto-cleanup: File: {path}')
                    except (OSError, RuntimeError) as e:
                        rollback()
                        raise cr_exc.InstallationStorageError(
                            f'Construction: Auto-cleanup: File: {path}:'
                            f' {type(e).__name__}: {e}'
                        ) from e
                    # Create a fresh DC/OS installation storage element
                    try:
                        path.mkdir(parents=True, exist_ok=True)
                        LOG.debug(f'{self.__class__.__name__}: Construction:'
                                  f' Create directory: {path}')
                    except (OSError, RuntimeError) as e:
                        rollback()
                        raise cr_exc.InstallationStorageError(
                            f'Construction: Create directory: {path}:'
                            f' {type(e).__name__}: {e}'
                        ) from e
                elif clean is True:
                    if clean_ready is True:
                        # Remove an existing DC/OS installation storage element
                        try:
                            cm_utl.rmdir(path=path, recursive=True)
                            LOG.debug(f'{self.__class__.__name__}:'
                                      f' Construction: Cleanup: {path}')
                        except (OSError, RuntimeError) as e:
                            rollback()
                            raise cr_exc.InstallationStorageError(
                                f'Construction: Cleanup: {path}:'
                                f' {type(e).__name__}: {e}'
                            ) from e
                        # Create a fresh DC/OS installation storage element
                        try:
                            path.mkdir(parents=True, exist_ok=True)
                            LOG.debug(f'{self.__class__.__name__}:'
                                      f' Construction: Create directory:'
                                      f' {path}')
                        except (OSError, RuntimeError) as e:
                            rollback()
                            raise cr_exc.InstallationStorageError(
                                f'Construction: Create directory: {path}:'
                                f' {type(e).__name__}: {e}'
                            ) from e
                    else:
                        rollback()
                        raise cr_exc.InstallationStorageError(
                            f'Construction:  Not ready for cleanup : {path}'
                        )
            else:
                # Create a fresh DC/OS installation storage element
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    rollback_path_list.append(path)
                    LOG.debug(f'{self.__class__.__name__}: Construction:'
                              f' Create directory: {path}')
                except (OSError, RuntimeError) as e:
                    rollback()
                    raise cr_exc.InstallationStorageError(
                        f'Construction: Create directory: {path}:'
                        f' {type(e).__name__}: {e}'
                    ) from e

    def destruct(self):
        """Remove entire existing DC/OS installation storage."""
        for path in self.istor_nodes[1:]:
            if path.is_absolute() and path.is_dir():
                try:
                    cm_utl.rmdir(path=path, recursive=True)
                    LOG.debug(f'{self.__class__.__name__}: Destruction:'
                              f' Remove directory: {path}')
                except (OSError, RuntimeError) as e:
                    raise cr_exc.InstallationStorageError(
                        f'Destruction: Remove directory: {path}:'
                        f' {type(e).__name__}: {e}'
                    )

    def get_pkgactive(self, manifest_loader=None):
        """Retrieve set of manifests of active packages.

        :param manifest_loader: callable, package manifest loader
        :return:                set, set of package manifest objects
        """
        assert callable(manifest_loader), (
            f'Argument: manifest_loader:'
            f' Got {type(manifest_loader).__name__} instead of callable'
        )

        pkg_manifests = set()

        # Path('/path/does/not/exist').glob('*') yields []
        for path in self.pkgactive_dpath.glob('*.json'):
            abs_path = self.pkgactive_dpath.joinpath(path)

            if abs_path.is_file():
                try:
                    pkg_manifests.add(manifest_loader(path))
                except cr_exc.RCError as e:
                    raise cr_exc.InstallationStorageError(
                        f'Get active package manifest:'
                        f' {path}: {type(e).__name__}: {e}'
                    ) from e

        return pkg_manifests

    @staticmethod
    def _make_pkg_url(pkg_id, dstor_root_url, dstor_pkgrepo_path):
        """Construct a direct URL to a package tarball at DC/OS distribution
        storage.

        :param pkg_id:             PackageId, package ID
        :param dstor_root_url:     str, DC/OS distribution storage root URL
        :param dstor_pkgrepo_path: str, DC/OS distribution storage package
                                   repository root path
        :return:                   str, direct DC/OS package tarball URL
        """
        pkg_url = posixpath.join(str(dstor_root_url), str(dstor_pkgrepo_path),
                                 pkg_id.pkg_name, f'{pkg_id.pkg_id}.tar.xz')

        return pkg_url

    def add_package(self, pkg_id, dstor_root_url, dstor_pkgrepo_path):
        """Add a package to the local package repository.

        :param pkg_id:             PackageId, package ID
        :param dstor_root_url:     str, DC/OS distribution storage root URL
        :param dstor_pkgrepo_path: str, DC/OS distribution storage package
                                   repository root path
        """
        msg_src = self.__class__.__name__
        # Download a package tarball
        pkg_url = self._make_pkg_url(pkg_id=pkg_id,
                                     dstor_root_url=dstor_root_url,
                                     dstor_pkgrepo_path=dstor_pkgrepo_path)
        try:
            cm_utl.download(pkg_url, str(self.tmp_dpath))
            LOG.debug(f'{msg_src}: Add package: Download: {pkg_id}: {pkg_url}')
        except Exception as e:
            raise cr_exc.RCDownloadError(
                f'Add package: {pkg_id}: {pkg_url}: {type(e).__name__}: {e}'
            ) from e
        # Unpack a package tarball
        pkgtarball_fpath = (
            self.tmp_dpath.joinpath(pkg_id.pkg_id).with_suffix('.tar.xz')
        )

        try:
            # Try to cleanup local package repository before trying to
            # create a package installation directory there
            pkg_inst_dpath = self.pkgrepo_dpath.joinpath(pkg_id.pkg_id)
            try:
                if pkg_inst_dpath.exists():
                    if pkg_inst_dpath.is_dir():
                        shutil.rmtree(str(pkg_inst_dpath))
                    elif pkg_inst_dpath.is_file and (
                        not pkg_inst_dpath.is_symlink()
                    ):
                        pkg_inst_dpath.unlink()
                    else:
                        raise cr_exc.InstallationStorageError(
                            f'Add package: {pkg_id}: Auto-cleanup'
                            f' package repository: Removing objects other than'
                            f' regular directories and files is not supported'
                        )
                    LOG.debug(f'{msg_src}: Add package: {pkg_id}: Auto-cleanup:'
                              f' {pkg_inst_dpath}')
            except (OSError, RuntimeError) as e:
                raise cr_exc.InstallationStorageError(
                    f'Add package: {pkg_id}: Auto-cleanup: {pkg_inst_dpath}:'
                    f' {type(e).__name__}: {e}'
                ) from e

            with tf.TemporaryDirectory(dir=str(self.tmp_dpath)) as temp_dpath:
                cm_utl.unpack(str(pkgtarball_fpath), temp_dpath)

                try:
                    # Lookup for a directory named after the package ID
                    src_dpath = [
                        path for path in Path(temp_dpath).iterdir() if (
                            path.name == pkg_id.pkg_id
                        )
                    ][0]
                    if src_dpath.is_dir():
                        shutil.copytree(
                            str(src_dpath), str(pkg_inst_dpath)
                        )
                    else:
                        # Only a directory may be named after the package ID,
                        # otherwise a package structure is broken
                        raise cr_exc.RCExtractError(
                            f'Add package: {pkg_id}: Broken package structure'
                        )
                except IndexError:
                    # Use the temporary directory as package's container
                    shutil.copytree(
                        temp_dpath, str(pkg_inst_dpath)
                    )

            LOG.debug(f'{msg_src}: Add package: Extract: {pkg_id}')
        except Exception as e:
            if not isinstance(e, cr_exc.RCExtractError):
                raise cr_exc.RCExtractError(
                    f'Add package: {pkg_id}: {type(e).__name__}: {e}'
                )
            else:
                raise
        finally:
            pkgtarball_fpath.unlink()
        # Create a work, runtime and log data directories for a package.
        for host_dpath in self.work_dpath, self.run_dpath, self.log_dpath:
            path = host_dpath.joinpath(pkg_id.pkg_name)

            if not path.exists():
                try:
                    path.mkdir(parents=True)
                    LOG.debug(f'{msg_src}: Add package: {pkg_id}:'
                              f' Create data directory: {path}')
                except (OSError, RuntimeError) as e:
                    raise cr_exc.InstallationStorageError(
                        f'Add package: {pkg_id}: Create data directory:'
                        f' {path}: {type(e).__name__}: {e}'
                    ) from e
            elif path.is_symlink():
                raise cr_exc.InstallationStorageError(
                        f'Add package: {pkg_id}: Create data directory:'
                        f' {path}: Symlink conflict'
                    )
            elif path.is_reserved():
                raise cr_exc.InstallationStorageError(
                    f'Add package: {pkg_id}: Create data directory:'
                    f' {path}: Reserved name conflict'
                )
            elif not path.is_dir():
                # Attempt to auto-clean garbage
                try:
                    path.unlink()
                    LOG.debug(f'{msg_src}: Add package: {pkg_id}: Auto-cleanup:'
                              f' File: {path}')
                except (OSError, RuntimeError) as e:
                    raise cr_exc.InstallationStorageError(
                        f'Add package: {pkg_id}: Auto-cleanup: File: {path}:'
                        f' {type(e).__name__}: {e}'
                    ) from e
                # Attempt to create data dir
                try:
                    path.mkdir(parents=True)
                    LOG.debug(f'{msg_src}: Add package: {pkg_id}:'
                              f' Create data directory: {path}')
                except (OSError, RuntimeError) as e:
                    raise cr_exc.InstallationStorageError(
                        f'Add package: {pkg_id}: Create data directory:'
                        f' {path}: {type(e).__name__}: {e}'
                    ) from e
            else:
                # Leave existing directories intact
                pass

        # Workaround for dcos-diagnostics to be able to start
        # TODO: Remove this code after correct dcos-diagnostics configuration
        #       is figured out and all its config files are arranged properly
        #       to support DC/OS installation storage FS layout.
        if pkg_id.pkg_name == 'dcos-diagnostics':
            # Move binary and config-files to DC/OS installation storage root
            src_dpath = self.pkgrepo_dpath.joinpath(pkg_id.pkg_id, 'bin')
            try:
                LOG.debug(
                    f'{msg_src}: Add package: Workaround: Copy list: '
                    f' {list(src_dpath.glob("*.*"))}'
                )
                for src_fpath in src_dpath.glob('*.*'):
                    if not self.root_dpath.joinpath(src_fpath.name).exists():
                        shutil.copy(str(src_fpath), str(self.root_dpath))
                        LOG.debug(
                            f'{msg_src}: Add package: Workaround: Copy file: '
                            f' {str(src_fpath)} -> {str(self.root_dpath)}'
                        )
                # Create a folder for logs
                log_dpath = self.root_dpath.joinpath('mesos-logs')
                if not log_dpath.exists():
                    log_dpath.mkdir()
            except Exception as e:
                raise cr_exc.RCExtractError(
                    f'Add package: {pkg_id}: {type(e).__name__}: {e}'
                )

    def remove_package(self, pkg_id):
        """Remove a package from the local package repository.

        :param pkg_id: PackageId, package ID
        """
        try:
            pkg_dpath = self.pkgrepo_dpath.joinpath(pkg_id.pkg_id)
            cm_utl.rmdir(str(pkg_dpath), recursive=True)
        except (OSError, RuntimeError) as e:
            raise cr_exc.RCRemoveError(
                f'Package {pkg_id.pkg_id}: {type(e).__name__}: {e}'
            )
