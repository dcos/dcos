"""Panda package management

Usage:
  pkgpanda activate <id>... [options]
  pkgpanda swap <package-id> [options]
  pkgpanda active [options]
  pkgpanda fetch --repository-url=<url> <id>... [options]
  pkgpanda add <package-tarball> [options]
  pkgpanda list [options]
  pkgpanda remove <id>... [options]
  pkgpanda setup [options]
  pkgpanda uninstall [options]
  pkgpanda check [--list] [options]

Options:
    --config-dir=<conf-dir>     Use an alternate directory for finding machine
                                configuration (roles, setup flags). [default: /etc/mesosphere/]
    --no-systemd                Don't try starting/stopping systemd services
    --no-block-systemd          Don't block waiting for systemd services to come up.
    --root=<root>               Testing only: Use an alternate root [default: /opt/mesosphere]
    --repository=<repository>   Testing only: Use an alternate local package
                                repository directory [default: /opt/mesosphere/packages]
    --rooted-systemd            Use $ROOT/dcos.target.wants for systemd management
                                rather than /etc/systemd/system/dcos.target.wants
"""

import os.path
import sys
from functools import partial
from itertools import groupby
from os import umask
from subprocess import CalledProcessError, check_call

from docopt import docopt

from pkgpanda import Install, PackageId, Repository, requests_fetcher
from pkgpanda.exceptions import FetchError, PackageError, ValidationError
from pkgpanda.util import (extract_tarball, if_exists, load_json, load_string,
                           write_string)


def add_to_repository(repository, path):
    # Extract Package Id (Filename must be path/{pkg-id}.tar.xz).
    name = os.path.basename(path)

    if not name.endswith('.tar.xz'):
        print("ERROR: Can only add package tarballs which have names " +
              "like {pkg-id}.tar.xz")

    pkg_id = name[:-len('.tar.xz')]

    # Validate the package id
    PackageId(pkg_id)

    def fetch(_, target):
        extract_tarball(path, target)

    repository.add(fetch, pkg_id)


def print_repo_list(packages):
    pkg_ids = list(map(PackageId, sorted(packages)))
    for name, group_iter in groupby(pkg_ids, lambda x: x.name):
        group = list(group_iter)
        if len(group) == 1:
            print(group[0])
        else:
            print(name + ':')
            for package in group:
                print("  " + package.version)


def _copy_fetcher(setup_pkg_dir, id, target):
    src_pkg_path = os.path.join(setup_pkg_dir, id) + "/"
    check_call(["cp", "-rp", src_pkg_path, target])


def do_bootstrap(install, repository):
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


dcos_target_contents = """[Install]
WantedBy=multi-user.target
"""


def start_dcos_target(no_systemd, noblock_systemd):
    if not no_systemd:
        no_block = ["--no-block"] if noblock_systemd else []
        check_call(["systemctl", "daemon-reload"])
        check_call(["systemctl", "enable", "dcos.target", '--no-reload'])
        check_call(["systemctl", "start", "dcos.target"] + no_block)


def setup(install, repository):

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
                     dcos_target_contents)
        do_bootstrap(install, repository)
        # Enable dcos.target only after we have populated it to prevent starting
        # up stuff inside of it before we activate the new set of packages.
        if install.manage_systemd:
            start_dcos_target(False, ['--no-block'])
        os.remove(bootstrap_path)

    # Check for /opt/mesosphere/install_progress. If found, recover the partial
    # update.
    if os.path.exists("/opt/mesosphere/install_progress"):
        took_action, msg = install.recover_swap_active()
        if not took_action:
            print("No recovery performed: {}".format(msg))


def do_activate(install, repository, ids, no_systemd, noblock_systemd):
    assert type(ids) == list
    try:
        install.activate(repository.load_packages(ids))
        start_dcos_target(no_systemd, noblock_systemd)

    except ValidationError as ex:
        print("Validation Error: {0}".format(ex))
        sys.exit(1)
    except PackageError as ex:
        print("Package Error: {0}".format(ex))


def uninstall(install, repository):
    print("Uninstalling DC/OS")
    # Remove dcos.target
    # TODO(cmaloney): Make this not quite so magical
    print("Removing dcos.target")
    print(os.path.dirname(install.systemd_dir) + "/dcos.target")
    check_call(['rm', '-f', os.path.dirname(install.systemd_dir) + "/dcos.target"])

    # Cleanup all systemd units
    # TODO(cmaloney): This is much more work than we need to do the job
    print("Deactivating all packages")
    install.activate([])

    # NOTE: All python libs need to be loaded before this so they are in-memory before we do the delete
    # Remove all well known files, directories
    # TODO(cmaloney): This should be a method of Install.
    print("Removing all runtime / activation directories")
    active_names = install.get_active_names()
    new_names = [name + '.new' for name in active_names]
    old_names = [name + '.old' for name in active_names]

    all_names = active_names + new_names + old_names

    assert len(all_names) > 0

    if '/' in all_names + [install.root]:
        print("Cowardly refusing to rm -rf '/' as part of uninstall.")
        print("Uninstall directories: ", ','.join(all_names + [install.root]))
        sys.exit(1)

    check_call(['rm', '-rf'] + all_names)

    # Removing /opt/mesosphere
    check_call(['rm', '-rf', install.root])


def find_checks(install, repository):
    checks = {}
    for active_package in install.get_active():
        tmp_checks = {}
        tmp_checks[active_package] = []
        package_check_dir = repository.load(active_package).check_dir
        if not os.path.isdir(package_check_dir):
            continue
        for check_file in sorted(os.listdir(package_check_dir)):
            if not os.access(os.path.join(package_check_dir, check_file), os.X_OK):
                print('WARNING: `{}` is not executable'.format(check_file),
                      file=sys.stderr)
                continue
            tmp_checks[active_package].append(check_file)
        if tmp_checks[active_package]:
            checks.update(tmp_checks)
    return checks


def list_checks(checks):
    for check_dir, check_files in sorted(checks.items()):
        print('{}'.format(check_dir))
        for check_file in check_files:
            print(' - {}'.format(check_file))


def run_checks(checks, install, repository):
    exit_code = 0
    for pkg_id, check_files in sorted(checks.items()):
        check_dir = repository.load(pkg_id).check_dir
        for check_file in check_files:
            try:
                check_call([os.path.join(check_dir, check_file)])
            except CalledProcessError:
                print('Check failed: {}'.format(check_file))
                exit_code = 1
    return exit_code


def main():
    arguments = docopt(__doc__, version="Pkpganda Package Manager")
    umask(0o022)

    # NOTE: Changing root or repository will likely break actually running packages.
    install = Install(
        os.path.abspath(arguments['--root']),
        os.path.abspath(arguments['--config-dir']),
        arguments['--rooted-systemd'],
        not arguments['--no-systemd'], not arguments['--no-block-systemd'])
    repository = Repository(os.path.abspath(arguments['--repository']))

    if arguments['setup']:
        try:
            setup(install, repository)
        except ValidationError as ex:
            print("Validation Error: {0}".format(ex))
            sys.exit(1)
        sys.exit(0)

    if arguments['list']:
        print_repo_list(repository.list())
        sys.exit(0)

    if arguments['active']:
        for pkg in sorted(install.get_active()):
            print(pkg)
        sys.exit(0)

    if arguments['add']:
        add_to_repository(repository, arguments['<package-tarball>'])
        sys.exit(0)

    if arguments['fetch']:
        def fetcher(id, target):
            return requests_fetcher(arguments['--repository-url'], id, target, os.getcwd())

        for pkg_id in arguments['<id>']:
            # TODO(cmaloney): Make this not use escape sequences when not at a
            # `real` terminal.
            sys.stdout.write("\rFetching: {0}".format(pkg_id))
            sys.stdout.flush()
            try:
                repository.add(fetcher, pkg_id)
            except FetchError as ex:
                print("\nUnable to fetch package {0}: {1}".format(pkg_id, ex))
                sys.exit(1)
            sys.stdout.write("\rFetched: {0}\n".format(pkg_id))
            sys.stdout.flush()

        sys.exit(0)

    if arguments['activate']:
        do_activate(install, repository, arguments['<id>'], arguments['--no-systemd'], arguments['--no-block-systemd'])
        sys.exit(0)

    if arguments['swap']:
        active = install.get_active()
        # TODO(cmaloney): I guarantee there is a better way to write this and
        # I've written the same logic before...
        packages_by_name = dict()
        for id_str in active:
            pkg_id = PackageId(id_str)
            packages_by_name[pkg_id.name] = pkg_id

        new_id = PackageId(arguments['<package-id>'])
        if new_id.name not in packages_by_name:
            print("ERROR: No package with name {} currently active to swap with.".format(new_id.name))

        packages_by_name[new_id.name] = new_id
        new_active = list(map(str, packages_by_name.values()))
        # Activate with the new package name
        do_activate(install, repository, new_active, arguments['--no-systemd'], arguments['--no-block-systemd'])
        sys.exit(0)

    if arguments['remove']:
        # Make sure none of the packages are active
        active_packages = install.get_active()
        active = active_packages.intersection(set(arguments['<id>']))
        if len(active) > 0:
            print("Refusing to remove active packages {0}".format(" ".join(sorted(list(active)))))
            sys.exit(1)

        for pkg_id in arguments['<id>']:
            sys.stdout.write("\rRemoving: {0}".format(pkg_id))
            sys.stdout.flush()
            try:
                # Validate package id, that package is installed.
                PackageId(pkg_id)
                repository.remove(pkg_id)
            except ValidationError:
                print("\nInvalid package id {0}".format(pkg_id))
                sys.exit(1)
            except OSError as ex:
                print("\nError removing package {0}".format(pkg_id))
                print(ex)
                sys.exit(1)
            sys.stdout.write("\rRemoved: {0}\n".format(pkg_id))
            sys.stdout.flush()
        sys.exit(0)

    if arguments['uninstall']:
        uninstall(install, repository)
        sys.exit(0)

    if arguments['check']:
        checks = find_checks(install, repository)
        if arguments['--list']:
            list_checks(checks)
            sys.exit(0)
        # Run all checks
        sys.exit(run_checks(checks, install, repository))

    print("unknown command")
    sys.exit(1)


if __name__ == "__main__":
    main()
