import copy
import json
import multiprocessing
import os
import random
import shutil
import string
import tempfile
from contextlib import contextmanager
from os import chdir, getcwd, mkdir
from os.path import exists
from subprocess import CalledProcessError, check_call, check_output

import pkgpanda.build.constants
import pkgpanda.build.src_fetchers
from pkgpanda import expand_require as expand_require_exceptions
from pkgpanda import Install, PackageId, Repository
from pkgpanda.actions import add_package_file
from pkgpanda.constants import install_root, PKG_DIR, RESERVED_UNIT_NAMES
from pkgpanda.exceptions import FetchError, PackageError, ValidationError
from pkgpanda.util import (check_forbidden_services, download_atomic,
                           hash_checkout, is_windows, load_json, load_string, logger,
                           make_directory, make_file, make_tar, remove_directory, rewrite_symlinks, write_json,
                           write_string)


class BuildError(Exception):
    """An error while building something."""

    def __init__(self, msg: str):
        self.msg = msg

    def __str__(self):
        return self.msg


class DockerCmd:

    def __init__(self):
        self.volumes = dict()
        self.environment = dict()
        self.container = str()

    def run(self, name, cmd):
        container_name = "{}-{}".format(
            name, ''.join(
                random.choice(string.ascii_lowercase) for _ in range(10)
            )
        )

        docker = ["docker", "run", "--name={}".format(container_name)]

        if is_windows:
            # Default number of processes on Windows is 1, so bumping up to use all of them.
            # The default memory allowed on Windows is 1GB. Some packages (mesos is an example)
            # needs about 3.5gb to compile a single file. Therefore we need about 4gb per CPU.
            numprocs = os.environ.get('NUMBER_OF_PROCESSORS')
            docker += ["-m", "{0}gb".format(int(numprocs) * 4), "--cpu-count", numprocs]

        for host_path, container_path in self.volumes.items():
            docker += ["-v", "{0}:{1}".format(host_path, container_path)]

        for k, v in self.environment.items():
            docker += ["-e", "{0}={1}".format(k, v)]

        docker.append(self.container)
        docker += cmd
        check_call(docker)
        DockerCmd.clean(container_name)

    @staticmethod
    def clean(name):
        """Cleans up the specified container"""
        check_call(["docker", "rm", "-v", name])


def get_variants_from_filesystem(directory, extension):
    results = set()
    for filename in os.listdir(directory):
        # Skip things that don't end in the extension
        if not filename.endswith(extension):
            continue

        variant = filename[:-len(extension)]

        # Empty name variant shouldn't have a `.` following it
        if variant == '.':
            raise BuildError("Invalid filename {}. The \"default\" variant file should be just {}".format(
                filename, extension))

        # Empty / default variant is represented as 'None'.
        if variant == '':
            variant = None
        else:
            # Should be foo. since we've moved the extension.
            if variant[-1] != '.':
                raise BuildError("Invalid variant filename {}. Expected a '.' separating the "
                                 "variant name and extension '{}'.".format(filename, extension))
            variant = variant[:-1]

        results.add(variant)

    return results


def get_src_fetcher(src_info, cache_dir, working_directory):
    try:
        kind = src_info['kind']
        if kind not in pkgpanda.build.src_fetchers.all_fetchers:
            raise ValidationError("No known way to catch src with kind '{}'. Known kinds: {}".format(
                kind,
                pkgpanda.src_fetchers.all_fetchers.keys()))

        args = {
            'src_info': src_info,
            'cache_dir': cache_dir
        }

        if src_info['kind'] in ['git_local', 'url', 'url_extract']:
            args['working_directory'] = working_directory

        return pkgpanda.build.src_fetchers.all_fetchers[kind](**args)
    except ValidationError as ex:
        raise BuildError("Validation error when fetching sources for package: {}".format(ex))


class TreeInfo:

    ALLOWED_TREEINFO_KEYS = {'exclude', 'variants', 'core_package_list', 'bootstrap_package_list'}

    def __init__(self, treeinfo_dict):
        if treeinfo_dict.keys() > self.ALLOWED_TREEINFO_KEYS:
            raise BuildError(
                "treeinfo can only include the keys {}. Found {}".format(
                    self.ALLOWED_TREEINFO_KEYS, treeinfo_dict.keys()))

        self.excludes = set(self._get_package_list(treeinfo_dict, 'exclude'))
        self.core_package_list = set(self._get_package_list(treeinfo_dict, 'core_package_list', self.excludes))
        self.bootstrap_package_list = set(self._get_package_list(
            treeinfo_dict,
            'bootstrap_package_list',
            self.excludes))

        # List of mandatory package variants to include in the buildinfo.
        self.variants = treeinfo_dict.get('variants', dict())
        if not isinstance(self.variants, dict):
            raise BuildError("treeinfo variants must be a dictionary of package name to variant name")

    @staticmethod
    def _get_package_list(treeinfo_dict, key, excludes=None):
        """Return a list of package name strings from treeinfo_dict by key.

        If key isn't present in treeinfo_dict, an empty list is returned.

        """
        excludes = excludes or list()
        package_list = treeinfo_dict.get(key, list())

        # Validate package list.
        if not isinstance(package_list, list):
            raise BuildError("{} must be either null (meaning don't use) or a list of package names.".format(key))
        for package_name in package_list:
            if not isinstance(package_name, str):
                raise BuildError("{} must be a list of strings. Found a {} with the value: {}".format(
                    key, type(package_name), package_name))

            try:
                PackageId.validate_name(package_name)
            except ValidationError as ex:
                raise BuildError("Invalid package name in {}: {}".format(key, package_name)) from ex

            if package_name in excludes:
                raise BuildError("Package found in both exclude and {}: {}".format(key, package_name))

        return package_list


class PackageSet:

    def __init__(self, variant, treeinfo, package_store):
        self.variant = variant

        self.all_packages = self.package_tuples_with_dependencies(
            # If core_package_list is empty, default to all non-excluded packages.
            treeinfo.core_package_list or (package_store.packages_by_name.keys() - treeinfo.excludes),
            treeinfo,
            package_store
        )
        self.validate_package_tuples(self.all_packages, treeinfo, package_store)

        if treeinfo.bootstrap_package_list:
            self.bootstrap_packages = self.package_tuples_with_dependencies(
                treeinfo.bootstrap_package_list,
                treeinfo,
                package_store
            )
            self.validate_package_tuples(self.bootstrap_packages, treeinfo, package_store)
        else:
            self.bootstrap_packages = self.all_packages

        # Validate bootstrap packages are a subset of all packages.
        for package_name, variant in self.bootstrap_packages:
            if (package_name, variant) not in self.all_packages:
                raise BuildError("Bootstrap package {} (variant {}) not found in set of all packages".format(
                    package_name, pkgpanda.util.variant_name(variant)))

    @staticmethod
    def package_tuples_with_dependencies(package_names, treeinfo, package_store):
        package_tuples = set((name, treeinfo.variants.get(name)) for name in set(package_names))
        to_visit = list(package_tuples)
        while to_visit:
            package_tuple = to_visit.pop()
            for require in package_store.get_buildinfo(*package_tuple)['requires']:
                require_tuple = expand_require(require)
                if require_tuple not in package_tuples:
                    to_visit.append(require_tuple)
                    package_tuples.add(require_tuple)
        return package_tuples

    @staticmethod
    def validate_package_tuples(package_tuples, treeinfo, package_store):
        # Validate that all packages have the variant specified in treeinfo.
        for package_name, variant in package_tuples:
            treeinfo_variant = treeinfo.variants.get(package_name)
            if variant != treeinfo_variant:
                raise BuildError(
                    "package {} is supposed to have variant {} included in the tree according to the treeinfo, "
                    "but variant {} was found.".format(
                        package_name,
                        pkgpanda.util.variant_name(treeinfo_variant),
                        pkgpanda.util.variant_name(variant),
                    )
                )

        # Validate that all needed packages are built and not excluded by treeinfo.
        for package_name, variant in package_tuples:
            if (package_name, variant) not in package_store.packages:
                raise BuildError(
                    "package {} variant {} is needed (explicitly requested or as a requires) "
                    "but is not in the set of built packages.".format(
                        package_name,
                        pkgpanda.util.variant_name(variant),
                    )
                )
            if package_name in treeinfo.excludes:
                raise BuildError("package {} is needed (explicitly requested or as a requires) "
                                 "but is excluded according to the treeinfo.json.".format(package_name))


class PackageStore:

    def __init__(self, packages_dir, repository_url):
        self._builders = {}
        self._repository_url = repository_url.rstrip('/') if repository_url is not None else None
        self._packages_dir = packages_dir.rstrip('/')

        # Load all possible packages, making a dictionary from (name, variant) -> buildinfo
        self._packages = dict()
        self._packages_by_name = dict()
        self._package_folders = dict()

        # Load an upstream if one exists
        # TODO(cmaloney): Allow upstreams to have upstreams
        self._package_cache_dir = self._packages_dir + "/cache/packages"
        self._upstream_dir = self._packages_dir + "/cache/upstream/checkout"
        self._upstream = None
        self._upstream_package_dir = self._upstream_dir + "/packages"
        # TODO(cmaloney): Make it so the upstream directory can be kept around
        remove_directory(self._upstream_dir)
        upstream_config = self._packages_dir + '/upstream.json'
        if os.path.exists(upstream_config):
            try:
                self._upstream = get_src_fetcher(
                    load_optional_json(upstream_config),
                    self._packages_dir + '/cache/upstream',
                    packages_dir)
                self._upstream.checkout_to(self._upstream_dir)
                if os.path.exists(self._upstream_package_dir + "/upstream.json"):
                    raise Exception("Support for upstreams which have upstreams is not currently implemented")
            except Exception as ex:
                raise BuildError("Error fetching upstream: {}".format(ex))

        # Iterate through the packages directory finding all packages. Note this package dir comes
        # first, then we ignore duplicate definitions of the same package
        package_dirs = [self._packages_dir]
        if self._upstream:
            package_dirs.append(self._upstream_package_dir)

        for directory in package_dirs:
            for name in os.listdir(directory):
                package_folder = directory + '/' + name

                # Ignore files / non-directories
                if not os.path.isdir(package_folder):
                    continue

                # If we've already found this package, it means 1+ versions have been defined. Use
                # those and ignore everything in the upstreams.
                if name in self._packages_by_name:
                    continue

                if is_windows:
                    builder_folder = os.path.join(directory, name, 'docker.windows')
                else:
                    builder_folder = os.path.join(directory, name, 'docker')
                if os.path.exists(builder_folder):
                    self._builders[name] = builder_folder

                # Search the directory for buildinfo.json files, record the variants
                for variant in get_variants_from_filesystem(package_folder, 'buildinfo.json'):
                    # Only adding the default dictionary once we know we have a package.
                    self._packages_by_name.setdefault(name, dict())

                    buildinfo = load_buildinfo(package_folder, variant)
                    self._packages[(name, variant)] = buildinfo
                    self._packages_by_name[name][variant] = buildinfo

                    if name in self._package_folders:
                        assert self._package_folders[name] == package_folder
                    else:
                        self._package_folders[name] = package_folder

    def get_package_folder(self, name):
        return self._package_folders[name]

    def get_bootstrap_cache_dir(self):
        return self._packages_dir + "/cache/bootstrap"

    def get_complete_cache_dir(self):
        return self._packages_dir + "/cache/complete"

    def get_buildinfo(self, name, variant):
        return self._packages[(name, variant)]

    def get_last_complete_set(self, variants):
        def get_last_complete(variant):
            complete_latest = (
                self.get_complete_cache_dir() + '/' + pkgpanda.util.variant_prefix(variant) + 'complete.latest.json')
            if not os.path.exists(complete_latest):
                raise BuildError("No last complete found for variant {}. Expected to find {} to match "
                                 "{}".format(pkgpanda.util.variant_name(variant), complete_latest,
                                             pkgpanda.util.variant_prefix(variant) + 'treeinfo.json'))
            return load_json(complete_latest)

        result = {}
        if variants is None:
            # Get all defined variants.
            requested_variants = self.list_trees()
        else:
            requested_variants = variants
        for variant in requested_variants:
            result[variant] = get_last_complete(variant)
        return result

    def get_last_build_filename(self, name, variant):
        return self.get_package_cache_folder(name) + '/{}latest'.format(pkgpanda.util.variant_prefix(variant))

    def get_package_path(self, pkg_id):
        return self.get_package_cache_folder(pkg_id.name) + '/{}.tar.xz'.format(pkg_id)

    def get_package_cache_folder(self, name):
        directory = self._package_cache_dir + '/' + name
        make_directory(directory)
        return directory

    def list_trees(self):
        return get_variants_from_filesystem(self._packages_dir, 'treeinfo.json')

    def get_package_set(self, variant):
        return PackageSet(variant, TreeInfo(load_config_variant(self._packages_dir, variant, 'treeinfo.json')), self)

    def get_all_package_sets(self):
        return [self.get_package_set(variant) for variant in sorted(self.list_trees(), key=pkgpanda.util.variant_str)]

    @property
    def packages(self):
        return self._packages

    @property
    def builders(self):
        return self._builders.copy()

    @property
    def packages_by_name(self):
        return self._packages_by_name

    @property
    def packages_dir(self):
        return self._packages_dir

    def try_fetch_by_id(self, pkg_id: PackageId):
        if self._repository_url is None:
            return False

        # TODO(cmaloney): Use storage providers to download instead of open coding.
        pkg_path = "{}.tar.xz".format(pkg_id)
        url = self._repository_url + '/packages/{0}/{1}'.format(pkg_id.name, pkg_path)
        try:
            directory = self.get_package_cache_folder(pkg_id.name)
            # TODO(cmaloney): Move to some sort of logging mechanism?
            print("Attempting to download", pkg_id, "from", url, "to", directory)
            download_atomic(directory + '/' + pkg_path, url, directory)
            assert os.path.exists(directory + '/' + pkg_path)
            return directory + '/' + pkg_path
        except FetchError:
            return False

    def try_fetch_bootstrap_and_active(self, bootstrap_id):
        if self._repository_url is None:
            return False

        try:
            bootstrap_name = '{}.bootstrap.tar.xz'.format(bootstrap_id)
            active_name = '{}.active.json'.format(bootstrap_id)
            # TODO(cmaloney): Use storage providers to download instead of open coding.
            bootstrap_url = self._repository_url + '/bootstrap/' + bootstrap_name
            active_url = self._repository_url + '/bootstrap/' + active_name
            print("Attempting to download", bootstrap_name, "from", bootstrap_url)
            dest_dir = self.get_bootstrap_cache_dir()
            # Normalize to no trailing slash for repository_url
            download_atomic(dest_dir + '/' + bootstrap_name, bootstrap_url, self._packages_dir)
            print("Attempting to download", active_name, "from", active_url)
            download_atomic(dest_dir + '/' + active_name, active_url, self._packages_dir)
            return True
        except FetchError:
            return False


def expand_require(require):
    try:
        return expand_require_exceptions(require)
    except ValidationError as ex:
        raise BuildError(str(ex)) from ex


def get_docker_id(docker_name):
    return check_output(["docker", "inspect", "-f", "{{ .Id }}", docker_name]).decode('utf-8').strip()


def hash_files_in_folder(directory):
    """Given a relative path, hashes all files inside that folder and subfolders

    Returns a dictionary from filename to the hash of that file. If that whole
    dictionary is hashed, you get a hash of all the contents of the folder.

    This is split out from calculating the whole folder hash so that the
    behavior in different walking corner cases can be more easily tested.
    """
    assert not directory.startswith('/'), \
        "For the hash to be reproducible on other machines relative paths must always be used. " \
        "Got path: {}".format(directory)
    directory = directory.rstrip('/')
    file_hash_dict = {}
    # TODO(cmaloney): Disallow symlinks as they're hard to hash, people can symlink / copy in their
    # build steps if needed.
    for root, dirs, filenames in os.walk(directory):
        assert not root.startswith('/')
        for name in filenames:
            path = root + '/' + name
            base = path[len(directory) + 1:]
            file_hash_dict[base] = pkgpanda.util.sha1(path)

        # If the directory has files inside of it, then it'll be picked up implicitly. by the files
        # or folders inside of it. If it contains nothing, it wouldn't be picked up but the existence
        # is important, so added it with a value for it's hash not-makeable via sha1 (empty string).
        if len(filenames) == 0 and len(dirs) == 0:
            path = root[len(directory) + 1:]
            # Empty path means it is the root directory, in which case we want no entries, not a
            # single entry "": ""
            if path:
                file_hash_dict[root[len(directory) + 1:]] = ""

    return file_hash_dict


@contextmanager
def as_cwd(path):
    start_dir = getcwd()
    chdir(path)
    yield
    chdir(start_dir)


def hash_folder_abs(directory, work_dir):
    assert directory.startswith(work_dir), "directory must be inside work_dir: {} {}".format(directory, work_dir)
    assert not work_dir[-1] == '/', "This code assumes no trailing slash on the work_dir"

    with as_cwd(work_dir):
        return hash_folder(directory[len(work_dir) + 1:])


def hash_folder(directory):
    return hash_checkout(hash_files_in_folder(directory))


# Try to read json from the given file. If it is an empty file, then return an
# empty json dictionary.
def load_optional_json(filename):
    try:
        with open(filename) as f:
            text = f.read().strip()
            if text:
                return json.loads(text)
            return {}
    except OSError as ex:
        raise BuildError("Failed to open JSON file {}: {}".format(filename, ex))
    except ValueError as ex:
        raise BuildError("Unable to parse json in {}: {}".format(filename, ex))


def load_config_variant(directory, variant, extension):
    assert directory[-1] != '/'
    return load_optional_json(directory + '/' + pkgpanda.util.variant_prefix(variant) + extension)


def load_buildinfo(path, variant):
    buildinfo = load_config_variant(path, variant, 'buildinfo.json')

    # Fill in default / guaranteed members so code everywhere doesn't have to guard around it.
    default_build_script = 'build'
    if is_windows:
        default_build_script = 'build.ps1'
    buildinfo.setdefault('build_script', pkgpanda.util.variant_prefix(variant) + default_build_script)
    buildinfo.setdefault('docker', 'dcos/dcos-builder:dcos-builder_dockerdir-latest')
    buildinfo.setdefault('environment', dict())
    buildinfo.setdefault('requires', list())
    buildinfo.setdefault('state_directory', False)

    return buildinfo


def make_bootstrap_tarball(package_store, packages, variant):
    # Convert filenames to package ids
    pkg_ids = list()
    for pkg_path in packages:
        # Get the package id from the given package path
        filename = os.path.basename(pkg_path)
        if not filename.endswith(".tar.xz"):
            raise BuildError("Packages must be packaged / end with a .tar.xz. Got {}".format(filename))
        pkg_id = filename[:-len(".tar.xz")]
        pkg_ids.append(pkg_id)

    bootstrap_cache_dir = package_store.get_bootstrap_cache_dir()

    # Filename is output_name.<sha-1>.{active.json|.bootstrap.tar.xz}
    bootstrap_id = hash_checkout(pkg_ids)
    latest_name = "{}/{}bootstrap.latest".format(bootstrap_cache_dir, pkgpanda.util.variant_prefix(variant))

    output_name = bootstrap_cache_dir + '/' + bootstrap_id + '.'

    # bootstrap tarball = <sha1 of packages in tarball>.bootstrap.tar.xz
    bootstrap_name = "{}bootstrap.tar.xz".format(output_name)
    active_name = "{}active.json".format(output_name)

    def mark_latest():
        # Ensure latest is always written
        write_string(latest_name, bootstrap_id)

        print("bootstrap: {}".format(bootstrap_name))
        print("active: {}".format(active_name))
        print("latest: {}".format(latest_name))
        return bootstrap_id

    if (os.path.exists(bootstrap_name)):
        print("Bootstrap already up to date, not recreating")
        return mark_latest()

    make_directory(bootstrap_cache_dir)

    # Try downloading.
    if package_store.try_fetch_bootstrap_and_active(bootstrap_id):
        print("Bootstrap already up to date, Not recreating. Downloaded from repository-url.")
        return mark_latest()

    print("Unable to download from cache. Building.")

    print("Creating bootstrap tarball for variant {}".format(variant))

    work_dir = tempfile.mkdtemp(prefix='mkpanda_bootstrap_tmp')

    def make_abs(path):
        return os.path.join(work_dir, path)

    pkgpanda_root = make_abs("opt/mesosphere")
    repository = Repository(os.path.join(pkgpanda_root, "packages"))

    # Fetch all the packages to the root
    for pkg_path in packages:
        filename = os.path.basename(pkg_path)
        pkg_id = filename[:-len(".tar.xz")]

        def local_fetcher(id, target):
            shutil.unpack_archive(pkg_path, target, "gztar")
        repository.add(local_fetcher, pkg_id, False)

    # Activate the packages inside the repository.
    # Do generate dcos.target.wants inside the root so that we don't
    # try messing with /etc/systemd/system.
    install = Install(
        root=pkgpanda_root,
        config_dir=None,
        rooted_systemd=True,
        manage_systemd=False,
        block_systemd=True,
        fake_path=True,
        skip_systemd_dirs=True,
        manage_users=False,
        manage_state_dir=False)
    install.activate(repository.load_packages(pkg_ids))

    # Mark the tarball as a bootstrap tarball/filesystem so that
    # dcos-setup.service will fire.
    make_file(make_abs("opt/mesosphere/bootstrap"))

    # Write out an active.json for the bootstrap tarball
    write_json(active_name, pkg_ids)

    # Rewrite all the symlinks to point to /opt/mesosphere
    rewrite_symlinks(work_dir, work_dir, "/")

    make_tar(bootstrap_name, pkgpanda_root)

    remove_directory(work_dir)

    # Update latest last so that we don't ever use partially-built things.
    write_string(latest_name, bootstrap_id)

    print("Built bootstrap")
    return mark_latest()


def build_tree_variants(package_store, mkbootstrap):
    """ Builds all possible tree variants in a given package store
    """
    result = dict()
    tree_variants = get_variants_from_filesystem(package_store.packages_dir, 'treeinfo.json')
    if len(tree_variants) == 0:
        raise Exception('No treeinfo.json can be found in {}'.format(package_store.packages_dir))
    for variant in tree_variants:
        result[variant] = pkgpanda.build.build_tree(package_store, mkbootstrap, variant)
    return result


def build_tree(package_store, mkbootstrap, tree_variants):
    """Build packages and bootstrap tarballs for one or all tree variants.

    Returns a dict mapping tree variants to bootstrap IDs.

    If tree_variant is None, builds all available tree variants.

    """
    # TODO(cmaloney): Add support for circular dependencies. They are doable
    # long as there is a pre-built version of enough of the packages.

    # TODO(cmaloney): Make it so when we're building a treeinfo which has a
    # explicit package list we don't build all the other packages.
    build_order = list()
    visited = set()
    built = set()

    def visit(pkg_tuple: tuple):
        """Add a package and its requires to the build order.

        Raises AssertionError if pkg_tuple is in the set of visited packages.

        If the package has any requires, they're recursively visited and added
        to the build order depth-first. Then the package itself is added.

        """

        # Visit the node for the first (and only) time.
        assert pkg_tuple not in visited
        visited.add(pkg_tuple)

        # Ensure all dependencies are built. Sorted for stability.
        # Requirements may be either strings or dicts, so we convert them all to (name, variant) tuples before sorting.
        for require_tuple in sorted(expand_require(r) for r in package_store.packages[pkg_tuple]['requires']):
            # If the dependency has already been built, we can move on.
            if require_tuple in built:
                continue
            # If the dependency has not been built but has been visited, then
            # there's a cycle in the dependency graph.
            if require_tuple in visited:
                raise BuildError("Circular dependency. Circular link {0} -> {1}".format(pkg_tuple, require_tuple))

            if PackageId.is_id(require_tuple[0]):
                raise BuildError("Depending on a specific package id is not supported. Package {} "
                                 "depends on {}".format(pkg_tuple, require_tuple))

            if require_tuple not in package_store.packages:
                raise BuildError("Package {0} require {1} not buildable from tree.".format(pkg_tuple, require_tuple))

            # Add the dependency (after its dependencies, if any) to the build
            # order.
            visit(require_tuple)

        build_order.append(pkg_tuple)
        built.add(pkg_tuple)

    # Can't compare none to string, so expand none -> "true" / "false", then put
    # the string in a field after "" if none, the string if not.
    def key_func(elem):
        return elem[0], elem[1] is None, elem[1] or ""

    def visit_packages(package_tuples):
        for pkg_tuple in sorted(package_tuples, key=key_func):
            if pkg_tuple in visited:
                continue
            visit(pkg_tuple)

    if tree_variants:
        package_sets = [package_store.get_package_set(v) for v in tree_variants]
    else:
        package_sets = package_store.get_all_package_sets()

    with logger.scope("resolve package graph"):
        # Build all required packages for all tree variants.
        for package_set in package_sets:
            visit_packages(package_set.all_packages)

    built_packages = dict()
    for (name, variant) in build_order:
        built_packages.setdefault(name, dict())

        # Run the build, store the built package path for later use.
        # TODO(cmaloney): Only build the requested variants, rather than all variants.
        built_packages[name][variant] = build(
            package_store,
            name,
            variant,
            True)

    # Build bootstrap tarballs for all tree variants.
    def make_bootstrap(package_set):
        with logger.scope("Making bootstrap variant: {}".format(pkgpanda.util.variant_name(package_set.variant))):
            package_paths = list()
            for name, pkg_variant in package_set.bootstrap_packages:
                package_paths.append(built_packages[name][pkg_variant])

            if mkbootstrap:
                return make_bootstrap_tarball(
                    package_store,
                    list(sorted(package_paths)),
                    package_set.variant)

    # Build bootstraps and and package lists for all variants.
    # TODO(cmaloney): Allow distinguishing between "build all" and "build the default one".
    complete_cache_dir = package_store.get_complete_cache_dir()
    make_directory(complete_cache_dir)
    results = {}
    for package_set in package_sets:
        info = {
            'bootstrap': make_bootstrap(package_set),
            'packages': sorted(
                load_string(package_store.get_last_build_filename(*pkg_tuple))
                for pkg_tuple in package_set.all_packages)}
        write_json(
            complete_cache_dir + '/' + pkgpanda.util.variant_prefix(package_set.variant) + 'complete.latest.json',
            info)
        results[package_set.variant] = info

    return results


def assert_no_duplicate_keys(lhs, rhs):
    if len(lhs.keys() & rhs.keys()) != 0:
        print("ASSERTION FAILED: Duplicate keys between {} and {}".format(lhs, rhs))
        assert len(lhs.keys() & rhs.keys()) == 0


# Find all build variants and build them
def build_package_variants(package_store, name, clean_after_build=True, recursive=False):
    # Find the packages dir / root of the packages tree, and create a PackageStore
    results = dict()
    for variant in package_store.packages_by_name[name].keys():
        results[variant] = build(
            package_store,
            name,
            variant,
            clean_after_build=clean_after_build,
            recursive=recursive)
    return results


class IdBuilder():

    def __init__(self, buildinfo):
        self._start_keys = set(buildinfo.keys())
        self._buildinfo = copy.deepcopy(buildinfo)
        self._taken = set()

    def _check_no_key(self, field):
        if field in self._buildinfo:
            raise BuildError("Key {} shouldn't be in buildinfo, but was".format(field))

    def add(self, field, value):
        self._check_no_key(field)
        self._buildinfo[field] = value

    def has(self, field):
        return field in self._buildinfo

    def take(self, field):
        self._taken.add(field)
        return self._buildinfo[field]

    def replace(self, taken_field, new_field, new_value):
        assert taken_field in self._buildinfo
        self._check_no_key(new_field)
        del self._buildinfo[taken_field]
        self._buildinfo[new_field] = new_value
        self._taken.add(new_field)

    def update(self, field, new_value):
        assert field in self._buildinfo
        self._buildinfo[field] = new_value

    def get_build_ids(self):
        # If any keys are left in the buildinfo, error that there were unused keys
        remaining_keys = self._start_keys - self._taken

        if remaining_keys:
            raise BuildError("ERROR: Unknown keys {} in buildinfo.json".format(remaining_keys))

        return self._buildinfo


def build(package_store: PackageStore, name: str, variant, clean_after_build, recursive=False):
    msg = "Building package {} variant {}".format(name, pkgpanda.util.variant_name(variant))
    with logger.scope(msg):
        return _build(package_store, name, variant, clean_after_build, recursive)


def _build(package_store, name, variant, clean_after_build, recursive):
    assert isinstance(package_store, PackageStore)
    tmpdir = tempfile.TemporaryDirectory(prefix="pkgpanda_repo")
    repository = Repository(tmpdir.name)

    package_dir = package_store.get_package_folder(name)

    def src_abs(name):
        return package_dir + '/' + name

    def cache_abs(filename):
        return package_store.get_package_cache_folder(name) + '/' + filename

    # Build pkginfo over time, translating fields from buildinfo.
    pkginfo = {}

    # Build up the docker command arguments over time, translating fields as needed.
    cmd = DockerCmd()

    assert (name, variant) in package_store.packages, \
        "Programming error: name, variant should have been validated to be valid before calling build()."

    builder = IdBuilder(package_store.get_buildinfo(name, variant))
    final_buildinfo = dict()

    builder.add('name', name)
    builder.add('variant', pkgpanda.util.variant_str(variant))

    # Convert single_source -> sources
    if builder.has('sources'):
        if builder.has('single_source'):
            raise BuildError('Both sources and single_source cannot be specified at the same time')
        sources = builder.take('sources')
    elif builder.has('single_source'):
        sources = {name: builder.take('single_source')}
        builder.replace('single_source', 'sources', sources)
    else:
        builder.add('sources', {})
        sources = dict()
        print("NOTICE: No sources specified")

    final_buildinfo['sources'] = sources

    # Construct the source fetchers, gather the checkout ids from them
    checkout_ids = dict()
    fetchers = dict()
    try:
        for src_name, src_info in sorted(sources.items()):
            # TODO(cmaloney): Switch to a unified top level cache directory shared by all packages
            cache_dir = package_store.get_package_cache_folder(name) + '/' + src_name
            make_directory(cache_dir)
            fetcher = get_src_fetcher(src_info, cache_dir, package_dir)
            fetchers[src_name] = fetcher
            checkout_ids[src_name] = fetcher.get_id()
    except ValidationError as ex:
        raise BuildError("Validation error when fetching sources for package: {}".format(ex))

    for src_name, checkout_id in checkout_ids.items():
        # NOTE: single_source buildinfo was expanded above so the src_name is
        # always correct here.
        # Make sure we never accidentally overwrite something which might be
        # important. Fields should match if specified (And that should be
        # tested at some point). For now disallowing identical saves hassle.
        assert_no_duplicate_keys(checkout_id, final_buildinfo['sources'][src_name])
        final_buildinfo['sources'][src_name].update(checkout_id)

    # Add the sha1 of the buildinfo.json + build file to the build ids
    builder.update('sources', checkout_ids)
    build_script_file = builder.take('build_script')
    # TODO(cmaloney): Change dest name to build_script_sha1
    builder.add('pkgpanda_version', pkgpanda.build.constants.version)

    extra_dir = src_abs("extra")
    # Add the "extra" folder inside the package as an additional source if it
    # exists
    if os.path.exists(extra_dir):
        extra_id = hash_folder_abs(extra_dir, package_dir)
        builder.add('extra_source', extra_id)
        final_buildinfo['extra_source'] = extra_id

    # Figure out the docker name.
    docker_name = builder.take('docker')
    cmd.container = docker_name

    # Add the id of the docker build environment to the build_ids.
    try:
        docker_id = get_docker_id(docker_name)
    except CalledProcessError:
        # docker pull the container and try again
        check_call(['docker', 'pull', docker_name])
        docker_id = get_docker_id(docker_name)

    builder.update('docker', docker_id)

    # TODO(cmaloney): The environment variables should be generated during build
    # not live in buildinfo.json.
    pkginfo['environment'] = builder.take('environment')

    # Whether pkgpanda should on the host make sure a `/var/lib` state directory is available
    pkginfo['state_directory'] = builder.take('state_directory')
    if pkginfo['state_directory'] not in [True, False]:
        raise BuildError("state_directory in buildinfo.json must be a boolean `true` or `false`")

    username = None
    if builder.has('username'):
        username = builder.take('username')
        if not isinstance(username, str):
            raise BuildError("username in buildinfo.json must be either not set (no user for this"
                             " package), or a user name string")
        try:
            pkgpanda.UserManagement.validate_username(username)
        except ValidationError as ex:
            raise BuildError("username in buildinfo.json didn't meet the validation rules. {}".format(ex))
        pkginfo['username'] = username

    group = None
    if builder.has('group'):
        group = builder.take('group')
        if not isinstance(group, str):
            raise BuildError("group in buildinfo.json must be either not set (use default group for this user)"
                             ", or group must be a string")
        try:
            pkgpanda.UserManagement.validate_group_name(group)
        except ValidationError as ex:
            raise BuildError("group in buildinfo.json didn't meet the validation rules. {}".format(ex))
        pkginfo['group'] = group

    # Packages need directories inside the fake install root (otherwise docker
    # will try making the directories on a readonly filesystem), so build the
    # install root now, and make the package directories in it as we go.
    install_dir = tempfile.mkdtemp(prefix="pkgpanda-")

    active_packages = list()
    active_package_ids = set()
    active_package_variants = dict()
    auto_deps = set()

    # Final package has the same requires as the build.
    requires = builder.take('requires')
    pkginfo['requires'] = requires

    if builder.has("sysctl"):
        pkginfo["sysctl"] = builder.take("sysctl")

    # TODO(cmaloney): Pull generating the full set of requires a function.
    to_check = copy.deepcopy(requires)
    if type(to_check) != list:
        raise BuildError("`requires` in buildinfo.json must be an array of dependencies.")
    while to_check:
        requires_info = to_check.pop(0)
        requires_name, requires_variant = expand_require(requires_info)

        if requires_name in active_package_variants:
            # TODO(cmaloney): If one package depends on the <default>
            # variant of a package and 1+ others depends on a non-<default>
            # variant then update the dependency to the non-default variant
            # rather than erroring.
            if requires_variant != active_package_variants[requires_name]:
                # TODO(cmaloney): Make this contain the chains of
                # dependencies which contain the conflicting packages.
                # a -> b -> c -> d {foo}
                # e {bar} -> d {baz}
                raise BuildError(
                    "Dependncy on multiple variants of the same package {}. variants: {} {}".format(
                        requires_name,
                        requires_variant,
                        active_package_variants[requires_name]))

            # The variant has package {requires_name, variant} already is a
            # dependency, don't process it again / move on to the next.
            continue

        active_package_variants[requires_name] = requires_variant

        # Figure out the last build of the dependency, add that as the
        # fully expanded dependency.
        requires_last_build = package_store.get_last_build_filename(requires_name, requires_variant)
        if not os.path.exists(requires_last_build):
            if recursive:
                # Build the dependency
                build(package_store, requires_name, requires_variant, clean_after_build, recursive)
            else:
                raise BuildError("No last build file found for dependency {} variant {}. Rebuild "
                                 "the dependency".format(requires_name, requires_variant))

        try:
            pkg_id_str = load_string(requires_last_build)
            auto_deps.add(pkg_id_str)
            pkg_buildinfo = package_store.get_buildinfo(requires_name, requires_variant)
            pkg_requires = pkg_buildinfo['requires']
            pkg_path = repository.package_path(pkg_id_str)
            pkg_tar = pkg_id_str + '.tar.xz'
            if not os.path.exists(package_store.get_package_cache_folder(requires_name) + '/' + pkg_tar):
                raise BuildError(
                    "The build tarball {} refered to by the last_build file of the dependency {} "
                    "variant {} doesn't exist. Rebuild the dependency.".format(
                        pkg_tar,
                        requires_name,
                        requires_variant))

            active_package_ids.add(pkg_id_str)

            # Mount the package into the docker container.
            cmd.volumes[pkg_path] = install_root + "/packages/{}:ro".format(pkg_id_str)
            os.makedirs(os.path.join(install_dir, "packages/{}".format(pkg_id_str)))

            # Add the dependencies of the package to the set which will be
            # activated.
            # TODO(cmaloney): All these 'transitive' dependencies shouldn't
            # be available to the package being built, only what depends on
            # them directly.
            to_check += pkg_requires
        except ValidationError as ex:
            raise BuildError("validating package needed as dependency {0}: {1}".format(requires_name, ex)) from ex
        except PackageError as ex:
            raise BuildError("loading package needed as dependency {0}: {1}".format(requires_name, ex)) from ex

    # Add requires to the package id, calculate the final package id.
    # NOTE: active_packages isn't fully constructed here since we lazily load
    # packages not already in the repository.
    builder.update('requires', list(active_package_ids))
    version_extra = None
    if builder.has('version_extra'):
        version_extra = builder.take('version_extra')

    build_ids = builder.get_build_ids()
    version_base = hash_checkout(build_ids)
    version = None
    if builder.has('version_extra'):
        version = "{0}-{1}".format(version_extra, version_base)
    else:
        version = version_base
    pkg_id = PackageId.from_parts(name, version)

    # Everything must have been extracted by now. If it wasn't, then we just
    # had a hard error that it was set but not used, as well as didn't include
    # it in the caluclation of the PackageId.
    builder = None

    # Save the build_ids. Useful for verify exactly what went into the
    # package build hash.
    final_buildinfo['build_ids'] = build_ids
    final_buildinfo['package_version'] = version

    # Save the package name and variant. The variant is used when installing
    # packages to validate dependencies.
    final_buildinfo['name'] = name
    final_buildinfo['variant'] = variant

    # If the package is already built, don't do anything.
    pkg_path = package_store.get_package_cache_folder(name) + '/{}.tar.xz'.format(pkg_id)

    # Done if it exists locally
    if exists(pkg_path):
        print("Package up to date. Not re-building.")

        # TODO(cmaloney): Updating / filling last_build should be moved out of
        # the build function.
        write_string(package_store.get_last_build_filename(name, variant), str(pkg_id))

        return pkg_path

    # Try downloading.
    dl_path = package_store.try_fetch_by_id(pkg_id)
    if dl_path:
        print("Package up to date. Not re-building. Downloaded from repository-url.")
        # TODO(cmaloney): Updating / filling last_build should be moved out of
        # the build function.
        write_string(package_store.get_last_build_filename(name, variant), str(pkg_id))
        print(dl_path, pkg_path)
        assert dl_path == pkg_path
        return pkg_path

    # Fall out and do the build since it couldn't be downloaded
    print("Unable to download from cache. Proceeding to build")

    print("Building package {} with buildinfo: {}".format(
        pkg_id,
        json.dumps(final_buildinfo, indent=2, sort_keys=True)))

    # Clean out src, result so later steps can use them freely for building.
    def clean():
        # Run a docker container to remove src/ and result/
        cmd = DockerCmd()
        cmd.volumes = {
            package_store.get_package_cache_folder(name): PKG_DIR + "/:rw",
        }
        if is_windows:
            cmd.container = "microsoft/windowsservercore:1709"
            filename = PKG_DIR + "\\src"
            cmd.run("package-cleaner",
                    ["cmd.exe", "/c", "if", "exist", filename, "rmdir", "/s", "/q", filename])
            filename = PKG_DIR + "\\result"
            cmd.run("package-cleaner",
                    ["cmd.exe", "/c", "if", "exist", filename, "rmdir", "/s", "/q", filename])
        else:
            cmd.container = "ubuntu:14.04.4"
            cmd.run("package-cleaner", ["rm", "-rf", PKG_DIR + "/src", PKG_DIR + "/result"])

    clean()

    # Only fresh builds are allowed which don't overlap existing artifacts.
    result_dir = cache_abs("result")
    if exists(result_dir):
        raise BuildError("result folder must not exist. It will be made when the package is "
                         "built. {}".format(result_dir))

    # 'mkpanda add' all implicit dependencies since we actually need to build.
    for dep in auto_deps:
        print("Auto-adding dependency: {}".format(dep))
        # NOTE: Not using the name pkg_id because that overrides the outer one.
        id_obj = PackageId(dep)
        add_package_file(repository, package_store.get_package_path(id_obj))
        package = repository.load(dep)
        active_packages.append(package)

    # Checkout all the sources int their respective 'src/' folders.
    try:
        src_dir = cache_abs('src')
        if os.path.exists(src_dir):
            raise ValidationError(
                "'src' directory already exists, did you have a previous build? " +
                "Currently all builds must be from scratch. Support should be " +
                "added for re-using a src directory when possible. src={}".format(src_dir))
        os.mkdir(src_dir)
        for src_name, fetcher in sorted(fetchers.items()):
            root = cache_abs('src/' + src_name)
            os.mkdir(root)

            fetcher.checkout_to(root)
    except ValidationError as ex:
        raise BuildError("Validation error when fetching sources for package: {}".format(ex))

    # Activate the packages so that we have a proper path, environment
    # variables.
    # TODO(cmaloney): RAII type thing for temproary directory so if we
    # don't get all the way through things will be cleaned up?
    install = Install(
        root=install_dir,
        config_dir=None,
        rooted_systemd=True,
        manage_systemd=False,
        block_systemd=True,
        fake_path=True,
        manage_users=False,
        manage_state_dir=False)
    install.activate(active_packages)
    # Rewrite all the symlinks inside the active path because we will
    # be mounting the folder into a docker container, and the absolute
    # paths to the packages will change.
    # TODO(cmaloney): This isn't very clean, it would be much nicer to
    # just run pkgpanda inside the package.
    rewrite_symlinks(install_dir, repository.path, install_root + "/packages/")

    print("Building package in docker")

    # TODO(cmaloney): Run as a specific non-root user, make it possible
    # for non-root to cleanup afterwards.
    # Run the build, prepping the environment as necessary.
    mkdir(cache_abs("result"))

    # Copy the build info to the resulting tarball
    write_json(cache_abs("src/buildinfo.full.json"), final_buildinfo)
    write_json(cache_abs("result/buildinfo.full.json"), final_buildinfo)

    write_json(cache_abs("result/pkginfo.json"), pkginfo)

    # Make the folder for the package we are building. If docker does it, it
    # gets auto-created with root permissions and we can't actually delete it.
    os.makedirs(os.path.join(install_dir, "packages", str(pkg_id)))

    # TOOD(cmaloney): Disallow writing to well known files and directories?
    # Source we checked out
    cmd.volumes.update({
        # TODO(cmaloney): src should be read only...
        # Source directory
        cache_abs("src"): PKG_DIR + "/src:rw",
        # Getting the result out
        cache_abs("result"): install_root + "/packages/{}:rw".format(pkg_id),
        # The build script directory
        package_dir: PKG_DIR + "/build:ro"
    })

    if is_windows:
        cmd.volumes.update({
            # todo: This is a temporary work around until Windows RS4 comes out that has a fix
            # that allows overlapping mount directories. We should not make this also happen
            # on Linux as it will probably break a bunch of stuff unnecessarily that will only
            # need to be undone in the future.
            install_dir: install_root + "/install_dir:ro"
        })
    else:
        cmd.volumes.update({
            install_dir: install_root + ":ro"
        })

    if os.path.exists(extra_dir):
        cmd.volumes[extra_dir] = PKG_DIR + "/extra:ro"
    cmd.environment = {
        "PKG_VERSION": version,
        "PKG_NAME": name,
        "PKG_ID": pkg_id,
        "PKG_PATH": install_root + "/packages/{}".format(pkg_id),
        "PKG_VARIANT": variant if variant is not None else "<default>",
        "NUM_CORES": multiprocessing.cpu_count()
    }

    try:
        # TODO(cmaloney): Run a wrapper which sources
        # /opt/mesosphere/environment then runs a build. Also should fix
        # ownership of /opt/mesosphere/packages/{pkg_id} post build.
        command = [PKG_DIR + "/build/" + build_script_file]
        cmd.run("package-builder", command)
    except CalledProcessError as ex:
        raise BuildError("docker exited non-zero: {}\nCommand: {}".format(ex.returncode, ' '.join(ex.cmd)))

    # Clean up the temporary install dir used for dependencies.
    # TODO(cmaloney): Move to an RAII wrapper.
    remove_directory(install_dir)

    with logger.scope("Build package tarball"):
        # Check for forbidden services before packaging the tarball:
        try:
            check_forbidden_services(cache_abs("result"), RESERVED_UNIT_NAMES)
        except ValidationError as ex:
            raise BuildError("Package validation failed: {}".format(ex))

        # TODO(cmaloney): Updating / filling last_build should be moved out of
        # the build function.
        write_string(package_store.get_last_build_filename(name, variant), str(pkg_id))

    # Bundle the artifacts into the pkgpanda package
    tmp_name = pkg_path + "-tmp.tar.xz"
    make_tar(tmp_name, cache_abs("result"))
    os.replace(tmp_name, pkg_path)
    print("Package built.")
    if clean_after_build:
        clean()
    return pkg_path
