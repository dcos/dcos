""" Test reading and changing the active set of available packages"""

import shutil

import pytest

from pkgpanda import Install, Repository
from pkgpanda.util import expect_fs, is_windows, resources_test_dir


@pytest.fixture
def repository():
    return Repository(str(resources_test_dir("packages")))


@pytest.fixture
def install():
        return Install(resources_test_dir("install"), resources_test_dir("systemd"), True, False, True)


# Test that the active set is detected correctly.
def test_active(install):
    active = install.get_active()
    assert type(active) is set

    assert active == {'mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8', 'mesos--0.22.0'}

    # TODO(cmaloney): More comprehensive testing of the validation checks

# TODO(cmaloney): All packages must be locally available in the repository


# TODO(cmaloney): No previous state, first active

# TODO(cmaloney): Updating active which is already full

# TODO(cmaloney): Activate failed, loading old/new

def test_recovery_noop(install):
    # No action if nothing to do
    action, _ = install.recover_swap_active()
    assert not action


def test_recovery_archive(tmpdir):
    # Recover from the "archive" state correctly.
    shutil.copytree(resources_test_dir("install_recovery_archive"), str(tmpdir.join("install")), symlinks=True)
    install = Install(str(tmpdir.join("install")), resources_test_dir("systemd"), True, False, True)
    action, _ = install.recover_swap_active()
    assert action

    # TODO(cmaloney): expect_fs
    if is_windows:
        expect_fs(
            str(tmpdir.join("install")),
            {
                ".gitignore": None,
                "active": ["mesos"],
                "active.buildinfo.full.json": None,
                "active.old": ["mesos"],
                "bin": ["mesos", "mesos-dir"],
                "dcos.target.wants": [".gitignore"],
                "environment": None,  # linux file ignored
                "environment.new": None,  # linux file ignored
                "environment.ps1": None,
                "environment.export.new": None,  # linux file ignored
                "environment.export.ps1": None,
                "environment.ps1.old": None,
                "etc": [".gitignore"],
                "include": [".gitignore"],
                "lib": ["libmesos.so"]
            })
    else:
        expect_fs(
            str(tmpdir.join("install")),
            {
                ".gitignore": None,
                "active": ["mesos"],
                "active.buildinfo.full.json": None,
                "active.old": ["mesos"],
                "bin": ["mesos", "mesos-dir"],
                "dcos.target.wants": [".gitignore"],
                "environment": None,
                "environment.ps1": None,  # windows file ignored
                "environment.ps1.new": None,  # windows file ignored
                "environment.export": None,
                "environment.export.ps1.new": None,  # windows file ignored
                "environment.old": None,
                "etc": [".gitignore"],
                "include": [".gitignore"],
                "lib": ["libmesos.so"]
            })


def test_recovery_move_new(tmpdir):
    # From the "move_new" state correctly.
    shutil.copytree(resources_test_dir("install_recovery_move"), str(tmpdir.join("install")), symlinks=True)
    install = Install(str(tmpdir.join("install")), resources_test_dir("systemd"), True, False, True)
    action, _ = install.recover_swap_active()
    assert action

    # TODO(cmaloney): expect_fs
    if is_windows:
        expect_fs(
            str(tmpdir.join("install")),
            {
                ".gitignore": None,
                "active": ["mesos"],
                "active.buildinfo.full.json": None,
                "bin": ["mesos", "mesos-dir"],
                "dcos.target.wants": [".gitignore"],
                "environment.ps1": None,
                "environment.export.ps1": None,
                "environment.new": None,  # linux files ignored
                "environment.export.new": None,  # linux files ignored
                "etc": [".gitignore"],
                "include": [".gitignore"],
                "lib": ["libmesos.so"]
            })
    else:
        expect_fs(
            str(tmpdir.join("install")),
            {
                ".gitignore": None,
                "active": ["mesos"],
                "active.buildinfo.full.json": None,
                "bin": ["mesos", "mesos-dir"],
                "dcos.target.wants": [".gitignore"],
                "environment": None,
                "environment.export": None,
                "environment.ps1.new": None,  # winodws files ignored
                "environment.export.ps1.new": None,  # windows files ignored
                "etc": [".gitignore"],
                "include": [".gitignore"],
                "lib": ["libmesos.so"]
            })
