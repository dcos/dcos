import collections
import os
import sys
from functools import partial
from subprocess import check_call

from pkgpanda import PackageId, requests_fetcher
from pkgpanda.exceptions import FetchError, PackageError, ValidationError
from pkgpanda.util import (extract_tarball, if_exists, load_json, load_string,
                           write_string)


DCOS_TARGET_CONTENTS = """[Install]
WantedBy=multi-user.target
"""


def activate_packages(install, repository, package_ids, systemd=True, block_systemd=False):
    """Replace the active package set with package_ids.

    install: pkgpanda.Install
    repository: pkgpanda.Repository
    package_ids: sequence of package IDs to activate
    systemd: start/stop systemd services (default: True)
    block_systemd: if systemd, block waiting for systemd services to come up (default: False)

    """
    assert isinstance(package_ids, collections.Sequence)
    try:
        install.activate(repository.load_packages(package_ids))
        _start_dcos_target(systemd, block_systemd)
    except ValidationError as ex:
        print("Validation Error: {0}".format(ex))
        sys.exit(1)
    except PackageError as ex:
        print("Package Error: {0}".format(ex))


def swap_active_package(install, repository, package_id, systemd=True, block_systemd=False):
    """Replace an active package with a package_id with the same name.

    swap(install, repository, 'foo--version') will replace the active 'foo'
    package with 'foo--version'.

    install: pkgpanda.Install
    repository: pkgpanda.Repository
    package_id: package ID to activate
    systemd: start/stop systemd services (default: True)
    block_systemd: if systemd, block waiting for systemd services to come up (default: False)

    """
    active = install.get_active()
    # TODO(cmaloney): I guarantee there is a better way to write this and
    # I've written the same logic before...
    packages_by_name = dict()
    for id_str in active:
        pkg_id = PackageId(id_str)
        packages_by_name[pkg_id.name] = pkg_id

    new_id = PackageId(package_id)
    if new_id.name not in packages_by_name:
        print("ERROR: No package with name {} currently active to swap with.".format(new_id.name))

    packages_by_name[new_id.name] = new_id
    new_active = list(map(str, packages_by_name.values()))
    # Activate with the new package name
    activate_packages(install, repository, new_active, systemd, block_systemd)


def fetch_package(repository, repository_url, package_id, work_dir):
    """Fetch package_id from repository_url into repository.

    repository: pkgpanda.Repository
    repository_url: URL for remote package repository
    package_id: package ID to fetch
    work_dir: location for temporary files, used only if repository_url is a file URL with a relative path

    """
    def fetcher(id_, target):
        return requests_fetcher(repository_url, id_, target, work_dir)

    # TODO(cmaloney): Make this not use escape sequences when not at a
    # `real` terminal.
    sys.stdout.write("\rFetching: {0}".format(package_id))
    sys.stdout.flush()
    try:
        repository.add(fetcher, package_id)
    except FetchError as ex:
        print("\nUnable to fetch package {0}: {1}".format(package_id, ex))
        sys.exit(1)
    sys.stdout.write("\rFetched: {0}\n".format(package_id))
    sys.stdout.flush()


def add_package_file(repository, package_filename):
    """Add a package to the repository from a file.

    repository: pkgpanda.Repository
    package_filename: location of the package file

    """
    filename_suffix = '.tar.xz'
    # Extract Package Id (Filename must be path/{pkg-id}.tar.xz).
    name = os.path.basename(package_filename)

    if not name.endswith(filename_suffix):
        print("ERROR: Can only add package tarballs which have names "
              "like {{pkg-id}}{}".format(filename_suffix))

    pkg_id = name[:-len(filename_suffix)]

    # Validate the package id
    PackageId(pkg_id)

    def fetch(_, target):
        extract_tarball(package_filename, target)

    repository.add(fetch, pkg_id)


def remove_package(install, repository, package_id):
    """Remove a package from the local repository.

    Errors if any packages in package_ids are activated in install.

    install: pkgpanda.Install
    repository: pkgpanda.Repository
    package_id: package ID to remove from repository

    """
    if package_id in install.get_active():
        print("Refusing to remove active package {0}".format(package_id))
        sys.exit(1)

    sys.stdout.write("\rRemoving: {0}".format(package_id))
    sys.stdout.flush()
    try:
        # Validate package id, that package is installed.
        PackageId(package_id)
        repository.remove(package_id)
    except ValidationError:
        print("\nInvalid package id {0}".format(package_id))
        sys.exit(1)
    except OSError as ex:
        print("\nError removing package {0}".format(package_id))
        print(ex)
        sys.exit(1)
    sys.stdout.write("\rRemoved: {0}\n".format(package_id))
    sys.stdout.flush()


def setup(install, repository):
    """Set up a fresh install of DC/OS.

    install: pkgpanda.Install
    repository: pkgpanda.Repository

    """
    # Check for /opt/mesosphere/bootstrap. If not exists, download everything
    # and install /etc/systemd/system/mutli-user.target/dcos.target
    bootstrap_path = os.path.join(install.root, "bootstrap")
    if os.path.exists(bootstrap_path):
        # Write, enable /etc/systemd/system/dcos.target for next boot.
        dcos_target_dir = os.path.dirname(install.systemd_dir)
        try:
            os.makedirs(dcos_target_dir)
        except FileExistsError:
            pass

        write_string(os.path.join(dcos_target_dir, "dcos.target"),
                     DCOS_TARGET_CONTENTS)
        _do_bootstrap(install, repository)
        # Enable dcos.target only after we have populated it to prevent starting
        # up stuff inside of it before we activate the new set of packages.
        if install.manage_systemd:
            _start_dcos_target(True, block_systemd=True)
        os.remove(bootstrap_path)

    # Check for /opt/mesosphere/install_progress. If found, recover the partial
    # update.
    if os.path.exists("/opt/mesosphere/install_progress"):
        took_action, msg = install.recover_swap_active()
        if not took_action:
            print("No recovery performed: {}".format(msg))


def _start_dcos_target(systemd, block_systemd):
    if systemd:
        no_block = [] if block_systemd else ["--no-block"]
        check_call(["systemctl", "daemon-reload"])
        check_call(["systemctl", "enable", "dcos.target", '--no-reload'])
        check_call(["systemctl", "start", "dcos.target"] + no_block)


def _do_bootstrap(install, repository):
    # These files should be set by the environment which initially builds
    # the host (cloud-init).
    repository_url = if_exists(load_string, install.get_config_filename("setup-flags/repository-url"))

    # TODO(cmaloney): If there is 1+ master, grab the active config from a master.
    # If the config can't be grabbed from any of them, fail.
    def fetcher(id, target):
        if repository_url is None:
            print("ERROR: Non-local package {} but no repository url given.".format(repository_url))
            sys.exit(1)
        return requests_fetcher(repository_url, id, target, os.getcwd())

    # Copy host/cluster-specific packages written to the filesystem manually
    # from the setup-packages folder into the repository. Do not overwrite or
    # merge existing packages, hard fail instead.
    setup_packages_to_activate = []
    setup_pkg_dir = install.get_config_filename("setup-packages")
    copy_fetcher = partial(_copy_fetcher, setup_pkg_dir)
    if os.path.exists(setup_pkg_dir):
        for pkg_id_str in os.listdir(setup_pkg_dir):
            print("Installing setup package: {}".format(pkg_id_str))
            if not PackageId.is_id(pkg_id_str):
                print("Invalid package id in setup package: {}".format(pkg_id_str))
                sys.exit(1)
            pkg_id = PackageId(pkg_id_str)
            if pkg_id.version != "setup":
                print("Setup packages (those in `{0}`) must have the version setup. Bad package: {1}"
                      .format(setup_pkg_dir, pkg_id_str))
                sys.exit(1)

            # Make sure there is no existing package
            if repository.has_package(pkg_id_str):
                print("WARNING: Ignoring already installed package {}".format(pkg_id_str))

            repository.add(copy_fetcher, pkg_id_str)
            setup_packages_to_activate.append(pkg_id_str)

    # If active.json is set on the host, use that as the set of packages to
    # activate. Otherwise just use the set of currently active packages (those
    # active in the bootstrap tarball)
    to_activate = None
    active_path = install.get_config_filename("setup-flags/active.json")
    if os.path.exists(active_path):
        print("Loaded active packages from", active_path)
        to_activate = load_json(active_path)

        # Ensure all packages are local
        print("Ensuring all packages in active set {} are local".format(",".join(to_activate)))
        for package in to_activate:
            repository.add(fetcher, package)
    else:
        print("Calculated active packages from bootstrap tarball")
        to_activate = list(install.get_active())

        # Fetch and activate all requested additional packages to accompany the bootstrap packages.
        cluster_packages_filename = install.get_config_filename("setup-flags/cluster-packages.json")
        cluster_packages = if_exists(load_json, cluster_packages_filename)
        print("Checking for cluster packages in:", cluster_packages_filename)
        if cluster_packages:
            if not isinstance(cluster_packages, list):
                print('ERROR: {} should contain a JSON list of packages. Got a {}'.format(cluster_packages_filename,
                                                                                          type(cluster_packages)))
            print("Loading cluster-packages: {}".format(cluster_packages))

            for package_id_str in cluster_packages:
                # Validate the package ids
                pkg_id = PackageId(package_id_str)

                # Fetch the packages if not local
                if not repository.has_package(package_id_str):
                    repository.add(fetcher, package_id_str)

                # Add the package to the set to activate
                setup_packages_to_activate.append(package_id_str)
        else:
            print("No cluster-packages specified")

    # Calculate the full set of final packages (Explicit activations + setup packages).
    # De-duplicate using a set.
    to_activate = list(set(to_activate + setup_packages_to_activate))

    print("Activating packages")
    install.activate(repository.load_packages(to_activate))


def _copy_fetcher(setup_pkg_dir, id_, target):
    src_pkg_path = os.path.join(setup_pkg_dir, id_) + "/"
    check_call(["cp", "-rp", src_pkg_path, target])
