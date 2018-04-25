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
                                configuration (roles, setup flags). [default: {default_config_dir}]
    --no-systemd                Don't try starting/stopping systemd services
    --no-block-systemd          Don't block waiting for systemd services to come up.
    --root=<root>               Testing only: Use an alternate root [default: {default_root}]
    --state-dir-root=<root>     Testing only: Use an alternate package state directory root
                                [default: {default_state_dir_root}]
    --repository=<repository>   Testing only: Use an alternate local package
                                repository directory [default: {default_repository}]
    --rooted-systemd            Use $ROOT/dcos.target.wants for systemd management
                                rather than /etc/systemd/system/dcos.target.wants
"""

import os
import sys
from itertools import groupby
from os import umask
from subprocess import CalledProcessError, check_call

from docopt import docopt

from pkgpanda import actions, constants, Install, PackageId, Repository
from pkgpanda.exceptions import PackageError, PackageNotFound, ValidationError
from pkgpanda.util import remove_directory, remove_file


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


def uninstall(install, repository):
    print("Uninstalling DC/OS")
    # Remove dcos.target
    # TODO(cmaloney): Make this not quite so magical
    print("Removing dcos.target")
    print(os.path.dirname(install.systemd_dir) + "/dcos.target")
    remove_file(os.path.dirname(install.systemd_dir) + "/dcos.target")

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
        print("Cowardly refusing to rm -rf '/' as part of uninstall.", file=sys.stderr)
        print("Uninstall directories: ", ','.join(all_names + [install.root]), file=sys.stderr)
        sys.exit(1)

    else:
        for name in all_names:
            remove_directory(name)

    # Removing /opt/mesosphere
    remove_directory(install.root)


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
                print('WARNING: `{}` is not executable'.format(check_file), file=sys.stderr)
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
                print('Check failed: {}'.format(check_file), file=sys.stderr)
                exit_code = 1
    return exit_code


def main():
    arguments = docopt(
        __doc__.format(
            default_config_dir=constants.config_dir,
            default_root=constants.install_root,
            default_repository=constants.repository_base,
            default_state_dir_root=constants.STATE_DIR_ROOT,
        ),
    )
    umask(0o022)

    # NOTE: Changing root or repository will likely break actually running packages.
    install = Install(
        os.path.abspath(arguments['--root']),
        os.path.abspath(arguments['--config-dir']),
        arguments['--rooted-systemd'],
        not arguments['--no-systemd'],
        not arguments['--no-block-systemd'],
        manage_users=True,
        add_users=not os.path.exists('/etc/mesosphere/manual_host_users'),
        manage_state_dir=True,
        state_dir_root=os.path.abspath(arguments['--state-dir-root']))

    repository = Repository(os.path.abspath(arguments['--repository']))

    try:
        if arguments['setup']:
            actions.setup(install, repository)
            sys.exit(0)

        if arguments['list']:
            print_repo_list(repository.list())
            sys.exit(0)

        if arguments['active']:
            for pkg in sorted(install.get_active()):
                print(pkg)
            sys.exit(0)

        if arguments['add']:
            actions.add_package_file(repository, arguments['<package-tarball>'])
            sys.exit(0)

        if arguments['fetch']:
            for package_id in arguments['<id>']:
                actions.fetch_package(
                    repository,
                    arguments['--repository-url'],
                    package_id,
                    os.getcwd())
            sys.exit(0)

        if arguments['activate']:
            actions.activate_packages(
                install,
                repository,
                arguments['<id>'],
                not arguments['--no-systemd'],
                not arguments['--no-block-systemd'])
            sys.exit(0)

        if arguments['swap']:
            actions.swap_active_package(
                install,
                repository,
                arguments['<package-id>'],
                not arguments['--no-systemd'],
                not arguments['--no-block-systemd'])
            sys.exit(0)

        if arguments['remove']:
            for package_id in arguments['<id>']:
                try:
                    actions.remove_package(install, repository, package_id)
                except PackageNotFound:
                    pass
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
    except ValidationError as ex:
        print("Validation Error: {0}".format(ex), file=sys.stderr)
        sys.exit(1)
    except PackageError as ex:
        print("Package Error: {0}".format(ex), file=sys.stderr)
        sys.exit(1)
    except Exception as ex:
        print("ERROR: {0}".format(ex), file=sys.stderr)
        sys.exit(1)

    print("unknown command", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
