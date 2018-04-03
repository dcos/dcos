import logging
import os
import sys
import tempfile
from subprocess import CalledProcessError, check_call
from typing import List

from gen import do_gen_package, resolve_late_package
from pkgpanda import PackageId, requests_fetcher
from pkgpanda.constants import (DCOS_SERVICE_CONFIGURATION_PATH,
                                install_root,
                                SYSCTL_SETTING_KEY)
from pkgpanda.exceptions import FetchError, PackageConflict, ValidationError
from pkgpanda.util import (download, extract_tarball, if_exists, load_json,
                           load_string, load_yaml, write_string)

DCOS_TARGET_CONTENTS = """[Install]
WantedBy=multi-user.target
"""

log = logging.getLogger(__name__)


def activate_packages(install, repository, package_ids, systemd, block_systemd):
    """Replace the active package set with package_ids.

    install: pkgpanda.Install
    repository: pkgpanda.Repository
    package_ids: sequence of package IDs to activate
    systemd: start/stop systemd services
    block_systemd: if systemd, block waiting for systemd services to come up

    """
    install.activate(repository.load_packages(package_ids))
    if systemd:
        _start_dcos_target(block_systemd)


def swap_active_package(install, repository, package_id, systemd, block_systemd):
    """Replace an active package with a package_id with the same name.

    swap(install, repository, 'foo--version') will replace the active 'foo'
    package with 'foo--version'.

    install: pkgpanda.Install
    repository: pkgpanda.Repository
    package_id: package ID to activate
    systemd: start/stop systemd services
    block_systemd: if systemd, block waiting for systemd services to come up

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
        raise ValidationError("No package with name {} currently active to swap with.".format(new_id.name))

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
        raise Exception("Unable to fetch package {0}: {1}".format(package_id, ex)) from ex
    else:
        sys.stdout.write("\rFetched: {0}".format(package_id))
    finally:
        sys.stdout.write("\n")
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
        raise ValidationError(
            "ERROR: Can only add package tarballs which have names like "
            "{{pkg-id}}{}".format(filename_suffix))

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
        raise PackageConflict("Refusing to remove active package {0}".format(package_id))

    sys.stdout.write("\rRemoving: {0}".format(package_id))
    sys.stdout.flush()
    try:
        # Validate package id, that package is installed.
        PackageId(package_id)
        repository.remove(package_id)
    except ValidationError as ex:
        raise ValidationError("Invalid package id {0}".format(package_id)) from ex
    except OSError as ex:
        raise Exception("Error removing package {0}: {1}".format(package_id, ex)) from ex
    else:
        sys.stdout.write("\rRemoved: {0}".format(package_id))
    finally:
        sys.stdout.write("\n")
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
            _start_dcos_target(block_systemd=True)
        os.remove(bootstrap_path)

    # Check for /opt/mesosphere/install_progress. If found, recover the partial
    # update.
    if os.path.exists(install_root + "/install_progress"):
        took_action, msg = install.recover_swap_active()
        if not took_action:
            print("No recovery performed: {}".format(msg))


def _start_dcos_target(block_systemd):
    no_block = [] if block_systemd else ["--no-block"]
    check_call(["systemctl", "daemon-reload"])
    check_call(["systemctl", "enable", "dcos.target", '--no-reload'])
    check_call(["systemctl", "start", "dcos.target"] + no_block)


def _get_package_list(package_list_id: str, repository_url: str) -> List[str]:
    package_list_url = repository_url + '/package_lists/{}.package_list.json'.format(package_list_id)
    with tempfile.NamedTemporaryFile() as f:
        download(f.name, package_list_url, os.getcwd(), rm_on_error=False)
        package_list = load_json(f.name)

    if not isinstance(package_list, list):
        raise ValidationError('{} should contain a JSON list of packages. Got a {}'.format(
            package_list_url, type(package_list)
        ))

    return package_list


def _do_bootstrap(install, repository):
    # These files should be set by the environment which initially builds
    # the host (cloud-init).
    repository_url = if_exists(load_string, install.get_config_filename("setup-flags/repository-url"))

    def fetcher(id, target):
        if repository_url is None:
            raise ValidationError("ERROR: Non-local package {} but no repository url given.".format(id))
        return requests_fetcher(repository_url, id, target, os.getcwd())

    setup_pkg_dir = install.get_config_filename("setup-packages")
    if os.path.exists(setup_pkg_dir):
        raise ValidationError(
            "setup-packages is no longer supported. It's functionality has been replaced with late "
            "binding packages. Found setup packages dir: {}".format(setup_pkg_dir))

    setup_packages_to_activate = []

    # If the host has late config values, build the late config package from them.
    late_config = if_exists(load_yaml, install.get_config_filename("setup-flags/late-config.yaml"))
    if late_config:
        pkg_id_str = late_config['late_bound_package_id']
        late_values = late_config['bound_values']
        print("Binding late config to late package {}".format(pkg_id_str))
        print("Bound values: {}".format(late_values))

        if not PackageId.is_id(pkg_id_str):
            raise ValidationError("Invalid late package id: {}".format(pkg_id_str))
        pkg_id = PackageId(pkg_id_str)
        if pkg_id.version != "setup":
            raise ValidationError("Late package must have the version setup. Bad package: {}".format(pkg_id_str))

        # Collect the late config package.
        with tempfile.NamedTemporaryFile() as f:
            download(
                f.name,
                repository_url + '/packages/{0}/{1}.dcos_config'.format(pkg_id.name, pkg_id_str),
                os.getcwd(),
                rm_on_error=False,
            )
            late_package = load_yaml(f.name)

        # Resolve the late package using the bound late config values.
        final_late_package = resolve_late_package(late_package, late_values)

        # Render the package onto the filesystem and add it to the package
        # repository.
        with tempfile.NamedTemporaryFile() as f:
            do_gen_package(final_late_package, f.name)
            repository.add(lambda _, target: extract_tarball(f.name, target), pkg_id_str)
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

        package_list_filename = install.get_config_filename("setup-flags/cluster-package-list")
        print("Checking for cluster packages in:", package_list_filename)
        package_list_id = if_exists(load_string, package_list_filename)
        if package_list_id:
            print("Cluster package list:", package_list_id)
            cluster_packages = _get_package_list(package_list_id, repository_url)
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


def _apply_sysctl(setting, service):
    try:
        check_call(["sysctl", "-q", "-w", setting])
    except CalledProcessError:
        log.warning("sysctl {setting} not set for {service}".format(setting=setting, service=service))


def _apply_sysctl_settings(sysctl_settings, service):
    for setting, value in sysctl_settings.get(service, {}).items():
        _apply_sysctl("{setting}={value}".format(setting=setting, value=value), service)


def apply_service_configuration(service):
    if not os.path.exists(DCOS_SERVICE_CONFIGURATION_PATH):
        return

    dcos_service_properties = load_json(DCOS_SERVICE_CONFIGURATION_PATH)
    if SYSCTL_SETTING_KEY in dcos_service_properties:
        _apply_sysctl_settings(dcos_service_properties[SYSCTL_SETTING_KEY], service)
