"""
See `docs/package_concepts.md` for the package layout.


Packages have ids. Ids are composed of a name + blob. The blob is never
introspected by the packaging stuff.

Each package contains a pkginfo.json. That contains a list of requires as well as
environment variables from the package.

"""
try:
    import grp
except ImportError:
    pass
import json
import os
import os.path
try:
    import pwd
except ImportError:
    pass
import re
import shutil
import sys
import tempfile
from collections import Iterable
from itertools import chain
from subprocess import CalledProcessError, check_call, check_output
from typing import Union

from pkgpanda.constants import (DCOS_SERVICE_CONFIGURATION_FILE,
                                RESERVED_UNIT_NAMES,
                                STATE_DIR_ROOT)
from pkgpanda.exceptions import (InstallError, PackageError, PackageNotFound,
                                 ValidationError)
from pkgpanda.util import (download, extract_tarball, if_exists, is_windows,
                           load_json, make_directory, remove_directory, write_json, write_string)

if not is_windows:
    assert 'grp' in sys.modules
    assert 'pwd' in sys.modules

# TODO(cmaloney): Can we switch to something like a PKGBUILD from ArchLinux and
# then just do the mutli-version stuff ourself and save a lot of re-implementation?

reserved_env_vars = ["LD_LIBRARY_PATH", "PATH"]

env_header = """# Pkgpanda provided environment variables
LD_LIBRARY_PATH={0}/lib
PATH={0}/bin:/usr/bin:/bin:/sbin\n\n"""

env_export_header = """# Pkgpanda provided environment variables
export LD_LIBRARY_PATH={0}/lib
export PATH="{0}/bin:$PATH"\n\n"""

name_regex = "^[a-zA-Z0-9@_+][a-zA-Z0-9@._+\-]*$"
version_regex = "^[a-zA-Z0-9@_+:.]+$"
username_regex = "^dcos_[a-z0-9_]+$"
linux_group_regex = "^[a-z_][a-z0-9_-]*$"  # https://github.com/shadow-maint/shadow/blob/master/libmisc/chkname.c#L52


class Systemd:
    """Manages systemd units and unit files during installation.

    This class uses a unit.wants directory as the list of all units it needs to manage. Unit files are copied to the
    base systemd dir to make sure they're available on the root volume, and thus readable when systemd starts. Symlinks
    in the unit.wants directory are rewritten to point to the copied unit files.

    """

    # Use "unit.new" to prevent removing unrelated ".new" directories if the install root is being used as the systemd
    # base dir.
    new_unit_suffix = ".unit.new"

    def __init__(self, unit_directory, active, block):
        self.__unit_directory = unit_directory
        self.__active = active
        self.__block = block
        self.__base_systemd = os.path.normpath(os.path.join(self.__unit_directory, ".."))

    def stop_all(self):
        if not self.__active:
            return
        if not os.path.exists(self.__unit_directory):
            return
        for name in os.listdir(self.__unit_directory):
            # Skip directories
            if os.path.isdir(os.path.join(self.__unit_directory, name)):
                continue
            try:
                cmd = ["systemctl", "stop", name]
                if not self.__block:
                    cmd.append("--no-block")
                check_call(cmd)
            except CalledProcessError as ex:
                # If the service doesn't exist, don't error. This happens when a
                # bootstrap tarball has just been extracted but nothing started
                # yet during first activation.
                if ex.returncode != 5:
                    raise

    def remove_staged_unit_files(self):
        """Remove staged unit files created by Systemd.stage_new_units()."""
        for filename in os.listdir(self.__base_systemd):
            if filename.endswith(self.new_unit_suffix):
                os.remove(os.path.join(self.__base_systemd, filename))

    def stage_new_units(self, new_wants_dir):
        """Prepare new systemd units for activation.

        Unit files targeted by the symlinks in new_wants_dir are copied to a temporary location in the base systemd
        directory, and the symlinks are rewritten to target the intended final destination of the copied unit files.

        """
        for unit_name in self.unit_names(new_wants_dir):
            wants_symlink_path = os.path.join(new_wants_dir, unit_name)
            package_file_path = os.path.realpath(wants_symlink_path)
            systemd_file_path = os.path.join(self.__base_systemd, unit_name)
            tmp_systemd_file_path = systemd_file_path + self.new_unit_suffix

            # Copy the unit file to the systemd directory with a suffix added to the filename.
            # This file will be moved to systemd_file_path when the new package set is swapped in.
            shutil.copyfile(package_file_path, tmp_systemd_file_path)
            shutil.copymode(package_file_path, tmp_systemd_file_path)

            # Rewrite the symlink to point to the copied unit file's destination.
            # This symlink won't point to the correct file until the copied unit file is moved to its target location
            # during activate_new_unit_files().
            os.remove(wants_symlink_path)
            os.symlink(systemd_file_path, wants_symlink_path)

    def remove_unit_files(self):
        if not os.path.exists(self.__unit_directory):
            return

        for unit_name in self.unit_names(self.__unit_directory):
            try:
                os.remove(os.path.join(self.__base_systemd, unit_name))
            except FileNotFoundError:
                pass

    def activate_new_unit_files(self):
        """Move new unit files to their final locations."""
        if not os.path.exists(self.__unit_directory):
            return

        self.remove_unit_files()

        for unit_name in self.unit_names(self.__unit_directory):
            systemd_file_path = os.path.join(self.__base_systemd, unit_name)
            os.rename(systemd_file_path + self.new_unit_suffix, systemd_file_path)

    @staticmethod
    def unit_names(unit_dir):
        units = os.listdir(unit_dir)
        for unit_name in units:
            if unit_name in RESERVED_UNIT_NAMES:
                raise Exception("Reserved name encountered - {}.".format(unit_name))
        return units

    @property
    def unit_directory(self):
        return self.__unit_directory


class PackageId:

    @staticmethod
    def parse(id: str):
        parts = id.split('--')
        if len(parts) != 2:
            raise ValidationError(
                "Invalid package id {0}. Package ids may only ".format(id) +
                "contain one '--' which seperates the name and version")

        PackageId.validate_name(parts[0])
        PackageId.validate_version(parts[1])

        return parts[0], parts[1]

    @staticmethod
    def from_parts(name, version):
        # TODO(cmaloney): This format, then parse is less than ideal.
        return PackageId("{0}--{1}".format(name, version))

    @staticmethod
    def validate_name(name):
        # [a-zA-Z0-9@._+-]
        # May not start with '.' or '-'.
        if not re.match(name_regex, name):
            raise ValidationError("Invalid package name {0}. Must match the regex {1}".format(name, name_regex))

    @staticmethod
    def is_id(package_str):
        return package_str.count('--') == 1

    @staticmethod
    def validate_version(version):
        # [a-zA-Z0-9@._+:]
        # May not contain a '-'.
        if not re.match(version_regex, version):
            raise ValidationError(
                "Invalid package version {0}. Must match the regex {1}".format(version, version_regex))

    def __init__(self, id):
        self.name, self.version = PackageId.parse(id)

    def __repr__(self):
        return '{0}--{1}'.format(self.name, self.version)


class Package:

    def __init__(self, path, id: Union[PackageId, str], pkginfo):
        if isinstance(id, str):
            id = PackageId(id)
        self.__id = id
        self.__path = path
        self.__pkginfo = pkginfo

    @property
    def environment(self):
        return self.__pkginfo.get('environment', dict())

    @property
    def sysctl(self):
        return self.__pkginfo.get('sysctl', dict())

    @property
    def check_dir(self):
        return self.__path + '/check'

    @property
    def id(self):
        return self.__id

    @property
    def name(self):
        return self.__id.name

    @property
    def path(self):
        return self.__path

    @property
    def variant(self):
        return self.__pkginfo.get('variant', None)

    @property
    def requires(self):
        return list(self.__pkginfo.get('requires', list()))

    @property
    def version(self):
        return self.__id.version

    @property
    def state_directory(self):
        return self.__pkginfo.get('state_directory', False)

    @property
    def username(self):
        return self.__pkginfo.get('username', None)

    @property
    def group(self):
        return self.__pkginfo.get('group', None)

    def __repr__(self):
        return str(self.__id)


def expand_require(require: Union[str, dict]):
    name = None
    variant = None
    if isinstance(require, str):
        name = require
    else:
        assert isinstance(require, dict)
        if 'name' not in require or 'variant' not in require:
            raise ValidationError(
                "When specifying a dependency in requires by dictionary to " +
                "depend on a variant both the name of the package and the " +
                "variant name must always be specified")
        name = require['name']
        variant = require['variant']

    if PackageId.is_id(name):
        raise ValidationError(
            "ERROR: Specifying a dependency on '" + name + "', an exact" +
            "package id isn't allowed. Dependencies may be specified by" +
            "package name alone or package name + variant (to change the" +
            "package variant).")

    return (name, variant)


# Check that a set of packages is reasonable.
def validate_compatible(packages, roles):
    # Every package name appears only once.
    names = set()
    ids = set()
    tuples = set()
    for package in packages:
        if package.name in names:
            raise ValidationError(
                "Repeated name {0} in set of packages {1}".format(
                    package.name, ' '.join(map(lambda x: str(x.id), packages))))

        if package.username is None and package.group is not None:
            raise ValidationError("`group` cannot be used without `username`")

        names.add(package.name)
        ids.add(str(package.id))
        tuples.add((package.name, package.variant))

    # All requires are met.
    # NOTE: Requires are given just to make it harder to accidentally
    # break a cluster.

    # Environment variables in packages, mapping from variable to package.
    environment = dict()
    sysctl_map = dict()

    for package in packages:

        # Check that all requirements of the package are met.
        # Requirements can be specified on a package name or full version string.
        for requirement in package.requires:
            name, variant = expand_require(requirement)
            if name not in names:
                raise ValidationError(
                    ("Package {} variant {} requires {} variant {} but that " +
                     "is not in the set of packages {}").format(
                        package.id,
                        package.variant,
                        name,
                        variant,
                        ', '.join(str(x.id) for x in packages)))

        # No repeated/conflicting environment variables with other packages as
        # well as magic system environment variables.
        for k, v in package.environment.items():
            if k in reserved_env_vars:
                raise ValidationError(
                    "{0} are reserved environment vars and cannot be specified in packages. Present in package {1}"
                    .format(", ".join(reserved_env_vars), package))
            if k in environment:
                raise ValidationError(
                    "Repeated environment variable {0}. In both packages {1} and {2}.".format(
                        k, v, package))
            environment[k] = package

        # No conflicting sysctl values.
        for service_name, sysctl_settings in package.sysctl.items():
            for sysctl_var, sysctl_value in sysctl_settings.items():
                if sysctl_var in sysctl_map and sysctl_map[sysctl_var] != sysctl_value:
                    raise ValueError(
                        "Conflicting sysctl setting {sysctl_var}={sysctl_value}"
                        " present in the service {service}".format(
                            sysctl_var=sysctl_var,
                            sysctl_value=sysctl_value,
                            service=service_name))

                sysctl_map[sysctl_var] = sysctl_value

    # TODO(cmaloney): More complete validation
    #  - There are no repeated file/folder in the well_known_dirs
    #       - Including the roles subfolders.
    #  - There is a base set of required package names (pkgpanda, mesos, config)
    #  - The config is for this specific type of host (master, slave)?


# TODO(cmaloney): Add a github fetcher, useful for grabbing config tarballs.
def requests_fetcher(base_url, id_str, target, work_dir):
    assert base_url
    assert type(id_str) == str
    id = PackageId(id_str)
    # TODO(cmaloney): That file:// urls are allowed in base_url is likely a security hole.
    # TODO(cmaloney): Switch to mesos-fetcher or aci or something so
    # all the logic can go away, we gain integrity checking, etc.
    base_url = base_url.rstrip('/')
    url = base_url + "/packages/{0}/{1}.tar.xz".format(id.name, id_str)
    # TODO(cmaloney): Use a private tmp directory so there is no chance of a user
    # intercepting the tarball + other validation data locally.
    with tempfile.NamedTemporaryFile(suffix=".tar.xz") as file:
        download(file.name, url, work_dir, rm_on_error=False)
        extract_tarball(file.name, target)


class Repository:

    def __init__(self, path):
        self.__path = os.path.abspath(path)
        self.__packages = None

    @property
    def path(self):
        return self.__path

    def package_path(self, id):
        return os.path.join(self.__path, id)

    def get_ids(self, name):
        # TODO(cmaloney): There is a lot of excess re-parsing here...
        return list(pkg_id for pkg_id in self.list() if PackageId(pkg_id).name == name)

    def has_package(self, id):
        return id in self.list()

    def list(self):
        """List the available packages in the repository.

        A package is a folder which contains a pkginfo.json"""
        if self.__packages is not None:
            return self.__packages

        packages = set()
        if not os.path.exists(self.__path):
            return packages

        for id in os.listdir(self.__path):
            if PackageId.is_id(id):
                packages.add(id)
        self.__packages = packages
        return self.__packages

    # Load the given package
    def load(self, id: str):

        # Validate the package id.
        PackageId(id)

        path = self.package_path(id)
        if not os.path.exists(path):
            raise PackageNotFound(id)

        filename = os.path.join(path, "pkginfo.json")
        try:
            pkginfo = load_json(filename)
        except OSError as ex:
            raise PackageError("No / unreadable pkginfo.json in {0}: {1}".format(id, ex.strerror)) from ex

        if not isinstance(pkginfo, dict):
            raise PackageError("Usage should be a dictionary, not a {0}".format(type(pkginfo).__name__))

        return Package(path, id, pkginfo)

    def load_packages(self, ids: Iterable):
        packages = set()
        for id in ids:
            packages.add(self.load(id))
        return packages

    def integrity_check(self):
        # Check that all packages in the local repository have valid
        # signatures, are up to date, all packages valid contents, etc.
        raise NotImplementedError()

    # Add the given package to the repository.
    # If the package is already in the repository does a no-op and returns false.
    # Returns true otherwise.
    def add(self, fetcher, id, warn_added=True):
        # Validate the package id.
        PackageId(id)

        # If the package already exists, return true
        package_path = self.package_path(id)
        if os.path.exists(package_path):
            if warn_added:
                print("Package already added.")
            return False

        # TODO(cmaloney): Supply a temporary directory to extract to
        # Then swap that into place, preventing partially-extracted things from
        # becoming an issue.
        pkg_path = self.package_path(id)
        # Appending _tmp so there is very little chance of us running into the
        # rm of another package, since all our PackageID strings are SHA-1, so
        # they never end with `_tmp`. `{sha}_tmp` is still a valid version
        # number however so other code doing directory scans will be fine with
        # the temp folders.
        tmp_path = pkg_path + '_tmp'

        # Cleanup artifacts (if any) laying around from previous partial
        # package extractions.
        remove_directory(tmp_path)

        fetcher(id, tmp_path)
        os.rename(tmp_path, pkg_path)
        return True

    def remove(self, id):
        path = self.package_path(id)
        if not os.path.exists(path):
            raise PackageNotFound(id)
        remove_directory(path)


class ConflictingFile(ValidationError):
    def __init__(self, src, dest, ex):
        super().__init__(ex)
        self.src = src
        self.dest = dest
        self.ex = ex


# Create folders and symlink files inside the folders. Allows multiple
# packages to have the same folder and provide it publicly.
def symlink_tree(src, dest):
    for name in os.listdir(src):
        src_path = os.path.join(src, name)
        dest_path = os.path.join(dest, name)
        # Symlink files and symlinks directly. For directories make a
        # real directory and symlink everything inside.
        # NOTE: We could relax this and follow symlinks, but then we
        # need to be careful about recursive filesystem layouts.
        if os.path.isdir(src_path) and not os.path.islink(src_path):
            if os.path.exists(dest_path):
                # We can only merge a directory into a directory.
                # We won't merge into a symlink directory because that could
                # result in a package editing inside another package.
                if not os.path.isdir(dest_path) and not os.path.islink(dest_path):
                    raise ValidationError(
                        "Can't merge a file `{0}` and directory (or symlink) `{1}` with the same name."
                        .format(src_path, dest_path))
            else:
                os.makedirs(dest_path)

            # Recurse into the directory symlinking everything so long as the directory isn't
            symlink_tree(src_path, dest_path)
        else:
            try:
                os.symlink(src_path, dest_path)
            except FileNotFoundError as ex:
                raise ConflictingFile(src_path, dest_path, ex) from ex


# Manages a systemd-sysusers user set.
# Can have users
class UserManagement:
    """Manages a systemd-sysusers configuration file / user set

    add_user() can be called until `ensure_users_exist` is called.
    get_uid() can only be called once `ensure_users_exist` is called.

    This helps enforce the code pattern which is needed to build one big sysusers configuration file
    and then create all the users / validate they all exist once. After that the users can be
    referenced / used.
    """

    def __init__(self, manage_users: bool, add_users: bool):
        self._manage_users = manage_users
        self._add_users = add_users
        self._users = set()

    @staticmethod
    def validate_username(username):
        if not re.match(username_regex, username):
            raise ValidationError("Username must begin with `dcos_` and only have a-z and underscore after that")

    @staticmethod
    def validate_group(group):
        # Empty group is allowed.
        if not group:
            return

        UserManagement.validate_group_name(group)

        try:
            grp.getgrnam(group)
        except KeyError:
            raise ValidationError("Group {} does not exist on the system".format(group))

    @staticmethod
    def validate_group_name(group_name):
        if not group_name:
            return

        if not re.match(linux_group_regex, group_name):
            raise ValidationError("Group {} has invalid name, must match the following regex: {}".format(
                group_name, linux_group_regex))

    @staticmethod
    def validate_user_group(username, group_name):
        user = pwd.getpwnam(username)
        if not group_name:
            return

        group = grp.getgrnam(group_name)
        if user.pw_gid != group.gr_gid:

            # check if the user is the right group, but the group is not primary.
            if username in group.gr_mem:
                return

            raise ValidationError(
                "User {} exists with current UID {}, however he should be assigned to group {} with {} UID, please "
                "check `buildinfo.json`".format(username, user.pw_gid, group_name, group.gr_gid))

    def add_user(self, username, groupname):
        UserManagement.validate_username(username)

        if not self._manage_users:
            return

        # Check if the user already exists and exit.
        try:
            if not is_windows:
                UserManagement.validate_user_group(username, groupname)
            self._users.add(username)
            return
        except KeyError as ex:
            # Doesn't exist, fall through
            pass

        # If we're not allowed to manage users, error
        if not self._add_users:
            raise ValidationError("User {} doesn't exist but is required by a DC/OS Component, and "
                                  "automatic user addition is disabled".format(username))

        # Add the user:
        add_user_cmd = [
            'useradd',
            '--system',
            '--home-dir', '/opt/mesosphere',
            '--shell', '/sbin/nologin',
            '-c', 'DCOS System User',
        ]

        # A group matching the username will be created by the adduser command.
        # Any other group that the user is added to needs to exist prior to executing the
        # adduser command.
        if groupname is not None and groupname != username:
            UserManagement.validate_group(groupname)
            add_user_cmd += [
                '-g', groupname
            ]

        add_user_cmd += [username]

        try:
            check_output(add_user_cmd)
            self._users.add(username)
        except CalledProcessError as ex:
            raise ValidationError("User {} doesn't exist and couldn't be created because of: {}"
                                  .format(username, ex.output))

    def get_uid(self, username):
        # Code should have already asserted all users exist, and be passing us
        # a user we know about. This method only works for package users.
        assert username in self._users

        return pwd.getpwnam(username).pw_uid


# A rooted install tree.
# Inside the install tree there will be all the well known folders and files as
# described in `docs/package_concepts.md`

class Install:

    # TODO(cmaloney) This is way too many options for these call points. Most
    # of these should be made so they can be removed (most are just for testing)

    def __init__(
            self,
            root,
            config_dir,
            rooted_systemd,
            manage_systemd,
            block_systemd,
            fake_path=False,
            skip_systemd_dirs=False,
            manage_users=False,
            add_users=False,
            manage_state_dir=False,
            state_dir_root=STATE_DIR_ROOT):

        assert type(rooted_systemd) == bool
        assert type(fake_path) == bool
        self.__root = os.path.abspath(root)
        self.__config_dir = os.path.abspath(config_dir) if config_dir else None
        if rooted_systemd:
            self.__systemd_dir = "{}/dcos.target.wants".format(root)
        else:
            self.__systemd_dir = "/etc/systemd/system/dcos.target.wants"

        self.__manage_systemd = manage_systemd
        self.__block_systemd = block_systemd

        # Look up the machine roles
        self.__roles = []
        if self.__config_dir:
            self.__roles = if_exists(os.listdir, os.path.join(self.__config_dir, "roles"))
            if self.__roles is None:
                self.__roles = []

        self.__well_known_dirs = ["bin", "etc", "include", "lib"]
        if not skip_systemd_dirs:
            self.__well_known_dirs.append(self.__systemd_dir)

        self.__fake_path = fake_path
        self.__skip_systemd_dirs = skip_systemd_dirs
        self.__manage_users = manage_users
        self.__add_users = add_users
        self.__manage_state_dir = manage_state_dir

        assert not state_dir_root.endswith('/')
        self.__state_dir_root = state_dir_root

        self.systemd = Systemd(self._make_abs(self.__systemd_dir), self.__manage_systemd, self.__block_systemd)

    def _get_dcos_configuration_template(self):
        return {"sysctl": {}}

    def get_active_dir(self):
        return os.path.join(self.__root, "active")

    def get_active(self):
        """the active folder has symlinks to all the active packages.

        Return the full package ids (The targets of the symlinks)."""
        active_dir = self.get_active_dir()

        if not os.path.exists(active_dir):
            if os.path.exists(active_dir + ".old") or os.path.exists(active_dir + ".new"):
                raise InstallError(
                    ("Broken past deploy. See {0}.new for what the (potentially incomplete) new state should be " +
                     "and optionally {0}.old if it exists for the complete previous state.").format(active_dir))
            else:
                raise InstallError(
                    "Install directory {0} has no active folder. Has it been bootstrapped?".format(self.__root))

        ids = set()
        for name in os.listdir(active_dir):
            package_path = os.path.realpath(os.path.join(active_dir, name))

            # NOTE: We don't validate the id here because we want to be able to
            # cope if there is something invalid in the current active dir.
            ids.add(os.path.basename(package_path))

        return ids

    def has_flag(self, name):
        return os.path.exists(self.get_config_filename(name))

    def get_config_filename(self, name):
        return os.path.join(self.__config_dir, name)

    def _make_abs(self, name):
        return os.path.abspath(os.path.join(self.__root, name))

    def get_active_names(self):
        return list(map(
            self._make_abs,
            self.__well_known_dirs + [
                "environment",
                "environment.export",
                "active",
                "active.buildinfo.full.json"
            ]))
    # Builds new working directories for the new active set, then swaps it into place as atomically as possible.

    def activate(self, packages):
        # Ensure the new set is reasonable.
        validate_compatible(packages, self.__roles)

        # Build the absolute paths for the running config, new config location,
        # and where to archive the config.
        active_names = self.get_active_names()
        active_dirs = list(map(self._make_abs, self.__well_known_dirs + ["active"]))

        new_names = [name + ".new" for name in active_names]
        new_dirs = [name + ".new" for name in active_dirs]

        old_names = [name + ".old" for name in active_names]

        # Remove all pre-existing new and old directories
        for name in chain(new_names, old_names):
            if os.path.exists(name):
                if os.path.isdir(name):
                    remove_directory(name)
                else:
                    os.remove(name)

        # Remove unit files staged for an activation that didn't occur.
        if not self.__skip_systemd_dirs:
            self.systemd.remove_staged_unit_files()

        # Make the directories for the new config
        for name in new_dirs:
            os.makedirs(name)

        def symlink_all(src, dest):
            if not os.path.isdir(src):
                return

            symlink_tree(src, dest)

        # Set the new LD_LIBRARY_PATH, PATH.
        env_contents = env_header.format("/opt/mesosphere" if self.__fake_path else self.__root)
        env_export_contents = env_export_header.format("/opt/mesosphere" if self.__fake_path else self.__root)

        active_buildinfo_full = {}

        dcos_service_configuration = self._get_dcos_configuration_template()

        # Building up the set of users
        sysusers = UserManagement(self.__manage_users, self.__add_users)

        def _get_service_files(_dir):
            service_files = []
            for root, directories, filenames in os.walk(_dir):
                for filename in filter(lambda name: name.endswith(".service"), filenames):
                    service_files.append(os.path.join(root, filename))
            return service_files

        def _get_service_names(_dir):
            service_files = list(map(os.path.basename, _get_service_files(_dir)))

            if not service_files:
                return []

            return list(map(lambda name: os.path.splitext(name)[0], service_files))

        # Add the folders, config in each package.
        for package in packages:
            # Package folders
            # NOTE: Since active is at the end of the folder list it will be
            # removed by the zip. This is the desired behavior, since it will be
            # populated later.
            # Do the basename since some well known dirs are full paths (dcos.target.wants)
            # while inside the packages they are always top level directories.
            for new, dir_name in zip(new_dirs, self.__well_known_dirs):
                dir_name = os.path.basename(dir_name)
                pkg_dir = os.path.join(package.path, dir_name)

                assert os.path.isabs(new)
                assert os.path.isabs(pkg_dir)

                try:
                    symlink_all(pkg_dir, new)

                    # Symlink all applicable role-based config
                    for role in self.__roles:
                        role_dir = os.path.join(package.path, "{0}_{1}".format(dir_name, role))
                        symlink_all(role_dir, new)

                except ConflictingFile as ex:
                    raise ValidationError("Two packages are trying to install the same file {0} or "
                                          "two roles in the set of roles {1} are causing a package "
                                          "to try activating multiple versions of the same file. "
                                          "One of the package files is {2}.".format(ex.dest,
                                                                                    self.__roles,
                                                                                    ex.src))

            # Add to the active folder
            os.symlink(package.path, os.path.join(self._make_abs("active.new"), package.name))

            # Add to the environment and environment.export contents

            env_contents += "# package: {0}\n".format(package.id)
            env_export_contents += "# package: {0}\n".format(package.id)

            for k, v in package.environment.items():
                env_contents += "{0}={1}\n".format(k, v)
                env_export_contents += "export {0}={1}\n".format(k, v)

            env_contents += "\n"
            env_export_contents += "\n"

            # Add to the buildinfo
            try:
                active_buildinfo_full[package.name] = load_json(os.path.join(package.path, "buildinfo.full.json"))
            except FileNotFoundError:
                # TODO(cmaloney): These only come from setup-packages. Should update
                # setup-packages to add a buildinfo.full for those packages
                active_buildinfo_full[package.name] = None

            # NOTE: It is critical the state dir, the package name and the user name are all the
            # same. Otherwise on upgrades we might remove access to a files by changing their chown
            # to something incompatible. We survive the first upgrade because everything goes from
            # root to specific users, and root can access all user files.
            if package.username is not None:
                sysusers.add_user(package.username, package.group)

            # Ensure the state directory exists
            # TODO(cmaloney): On upgrade take a snapshot?
            if self.__manage_state_dir:
                state_dir_path = self.__state_dir_root + '/' + package.name
                if package.state_directory:
                    make_directory(state_dir_path)
                    if package.username and not is_windows:
                        uid = sysusers.get_uid(package.username)
                        check_call(['chown', '-R', str(uid), state_dir_path])

            if package.sysctl:
                service_names = _get_service_names(package.path)

                if not service_names:
                    raise ValueError("service name required for sysctl could not be determined for {package}".format(
                        package=package.id))

                for service in service_names:
                    if service in package.sysctl:
                        dcos_service_configuration["sysctl"][service] = package.sysctl[service]

        # Prepare new systemd units for activation.
        if not self.__skip_systemd_dirs:
            new_wants_dir = self._make_abs(self.__systemd_dir + ".new")
            if os.path.exists(new_wants_dir):
                self.systemd.stage_new_units(new_wants_dir)

        dcos_service_configuration_file = os.path.join(self._make_abs("etc.new"), DCOS_SERVICE_CONFIGURATION_FILE)
        write_json(dcos_service_configuration_file, dcos_service_configuration)

        # Write out the new environment file.
        new_env = self._make_abs("environment.new")
        write_string(new_env, env_contents)

        # Write out the new environment.export file
        new_env_export = self._make_abs("environment.export.new")
        write_string(new_env_export, env_export_contents)

        # Write out the buildinfo of every active package
        new_buildinfo_meta = self._make_abs("active.buildinfo.full.json.new")
        write_json(new_buildinfo_meta, active_buildinfo_full)

        self.swap_active(".new")

    def recover_swap_active(self):
        state_filename = self._make_abs("install_progress")
        if not os.path.exists(state_filename):
            return False, "Path does not exist: {}".format(state_filename)
        state = load_json(state_filename)
        extension = state['extension']
        stage = state['stage']
        if stage == 'archive':
            self.swap_active(extension, True)
        elif stage == 'move_new':
            self.swap_active(extension, False)
        else:
            raise ValueError("Unexpected state to recover from {}".format(state))

        return True, ""
    # Does an atomic(ish) upgrade swap with support for recovering if
    # only part of the swap happens before a reboot.
    # TODO(cmaloney): Implement recovery properly.

    def swap_active(self, extension, archive=True):
        active_names = self.get_active_names()
        state_filename = self._make_abs("install_progress")

        # Ensure all the new active files exist
        for active in active_names:
            if not os.path.exists(active + extension):
                raise ValueError(
                    "Unable to swap active packages. Needed file {} doesn't exist.".format(active + extension))

        # Record the state (atomically) on the filesystem so that if there is a
        # hard/fast fail at any point the activate swap can continue.
        def record_state(state):
            # Atomically write all the state to disk, swap into place.
            with open(state_filename + ".new", "w+") as f:
                state['extension'] = extension
                json.dump(state, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(state_filename + ".new", state_filename)

        if archive:
            # TODO(cmaloney): stop all systemd services in dcos.target.wants
            record_state({"stage": "archive"})

            # Stop all systemd services and clean up existing unit files.
            if not self.__skip_systemd_dirs:
                self.systemd.stop_all()
                self.systemd.remove_unit_files()

            # Archive the current config.
            for active in active_names:
                old_path = active + ".old"
                if os.path.exists(active):
                    os.rename(active, old_path)

        record_state({"stage": "move_new"})

        # Move new / with extension into active.
        # TODO(cmaloney): Capture any failures here and roll-back if possible.
        # TODO(cmaloney): Alert for any failures here.
        for active in active_names:
            new_path = active + extension
            os.rename(new_path, active)

        if not self.__skip_systemd_dirs:
            self.systemd.activate_new_unit_files()

        # All done with what we need to redo if host restarts.
        os.remove(state_filename)

    @property
    def manage_systemd(self):
        return self.__manage_systemd

    @property
    def systemd_dir(self):
        return self.__systemd_dir

    @property
    def root(self):
        return self.__root
