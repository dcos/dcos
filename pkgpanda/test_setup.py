import os
from shutil import copytree
from subprocess import check_call, check_output

from pkgpanda.util import expect_fs, is_windows, islink, load_json, realpath, resources_test_dir, run


def tmp_repository(temp_dir, repo_dir=resources_test_dir("packages")):
    repo_path = temp_dir.join("repository")
    copytree(repo_dir, str(repo_path))
    return repo_path


def test_setup(tmpdir):
    repo_path = tmp_repository(tmpdir)
    tmpdir.join("root", "bootstrap").write("", ensure=True)

    check_call(["pkgpanda",
                "setup",
                "--root={0}/root".format(tmpdir),
                "--rooted-systemd",
                "--repository={}".format(repo_path),
                "--config-dir={}".format(resources_test_dir("etc-active")),
                "--no-systemd"
                ])

    expect_fs("{0}".format(tmpdir), ["repository", "root"])

    # TODO(cmaloney): Validate things got placed correctly.
    if is_windows:
        environment_extension = ".ps1"
    else:
        environment_extension = ""

    expect_fs(
        "{0}/root".format(tmpdir),
        {
            "active": ["dcos-provider-abcdef-test", "mesos", "mesos-config"],
            "active.buildinfo.full.json": None,
            "bin": [
                "mesos",
                "mesos-dir",
                "mesos-master",
                "mesos-slave"],
            "lib": ["libmesos.so"],
            "etc": ["dcos-service-configuration.json", "foobar", "some.json"],
            "include": [],
            "dcos.target.wants": ["dcos-mesos-master.service"],
            "dcos.target": None,
            "environment" + environment_extension: None,
            "environment.export" + environment_extension: None,
            "dcos-mesos-master.service": None           # rooted_systemd
        })

    expected_dcos_service_configuration = {
        "sysctl": {
            "dcos-mesos-master": {
                "kernel.watchdog_thresh": "11",
                "net.netfilter.nf_conntrack_udp_timeout": "30"
            },
            "dcos-mesos-slave": {
                "kperf.debug_level": "1"
            }
        }
    }

    assert expected_dcos_service_configuration == load_json(
        "{tmpdir}/root/etc/dcos-service-configuration.json".format(tmpdir=tmpdir))

    assert load_json('{0}/root/etc/some.json'.format(tmpdir)) == {
        'cluster-specific-stuff': 'magic',
        'foo': 'bar',
        'baz': 'qux',
    }

    # Introspection should work right
    active = set(check_output([
        "pkgpanda",
        "active",
        "--root={0}/root".format(tmpdir),
        "--rooted-systemd",
        "--repository={}".format(repo_path),
        "--config-dir={}".format(resources_test_dir("etc-active"))]).decode().split())

    assert active == {
        "dcos-provider-abcdef-test--setup",
        "mesos--0.22.0",
        "mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8",
    }
    tmpdir.join("root", "bootstrap").write("", ensure=True)
    # If we setup the same directory again we should get .old files.
    check_call(["pkgpanda",
                "setup",
                "--root={0}/root".format(tmpdir),
                "--rooted-systemd",
                "--repository={}".format(repo_path),
                "--config-dir={}".format(resources_test_dir("etc-active")),
                "--no-systemd"
                ])
    # TODO(cmaloney): Validate things got placed correctly.

    expect_fs(
        "{0}/root".format(tmpdir),
        {
            "active": ["dcos-provider-abcdef-test", "mesos", "mesos-config"],
            "active.buildinfo.full.json.old": None,
            "active.buildinfo.full.json": None,
            "bin": [
                "mesos",
                "mesos-dir",
                "mesos-master",
                "mesos-slave"],
            "lib": ["libmesos.so"],
            "etc": ["dcos-service-configuration.json", "foobar", "some.json"],
            "include": [],
            "dcos.target": None,
            "dcos.target.wants": ["dcos-mesos-master.service"],
            "environment" + environment_extension: None,
            "environment.export" + environment_extension: None,
            "active.old": ["dcos-provider-abcdef-test", "mesos", "mesos-config"],
            "bin.old": [
                "mesos",
                "mesos-dir",
                "mesos-master",
                "mesos-slave"],
            "lib.old": ["libmesos.so"],
            "etc.old": ["dcos-service-configuration.json", "foobar", "some.json"],
            "include.old": [],
            "dcos.target.wants.old": ["dcos-mesos-master.service"],
            "environment" + environment_extension + ".old": None,
            "environment.export" + environment_extension + ".old": None,
            "dcos-mesos-master.service": None       # rooted systemd
        })

    # Should only pickup the packages once / one active set.
    active = set(check_output([
        "pkgpanda",
        "active",
        "--root={0}/root".format(tmpdir),
        "--rooted-systemd",
        "--repository={}".format(repo_path),
        "--config-dir={}".format(resources_test_dir("etc-active"))]).decode().split())

    assert active == {
        "dcos-provider-abcdef-test--setup",
        "mesos--0.22.0",
        "mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8",
    }

    # Touch some .new files so we can be sure that deactivate cleans those up as well.
    tmpdir.mkdir("root/bin.new")
    tmpdir.mkdir("root/lib.new")
    tmpdir.mkdir("root/etc.new")
    tmpdir.mkdir("root/foo.new")
    tmpdir.mkdir("root/baz")
    tmpdir.mkdir("root/foobar.old")
    tmpdir.mkdir("root/packages")

    # Uninstall / deactivate everything,
    check_call(["pkgpanda",
                "uninstall",
                "--root={0}/root".format(tmpdir),
                "--rooted-systemd",
                "--repository={}".format(repo_path),
                "--config-dir={}".format(resources_test_dir("etc-active")),
                "--no-systemd"
                ])

    expect_fs("{0}".format(tmpdir), {"repository": None})


def test_activate(tmpdir):
    repo_path = tmp_repository(tmpdir)
    state_dir_root = tmpdir.join("package_state")
    tmpdir.join("root", "bootstrap").write("", ensure=True)

    # TODO(cmaloney): Depending on setup here is less than ideal, but meh.
    check_call(["pkgpanda",
                "setup",
                "--root={0}/root".format(tmpdir),
                "--rooted-systemd",
                "--repository={}".format(repo_path),
                "--config-dir={}".format(resources_test_dir("etc-active")),
                "--no-systemd"
                ])

    assert run(["pkgpanda",
                "activate",
                "mesos--0.22.0",
                "mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8",
                "--root={0}/root".format(tmpdir),
                "--rooted-systemd",
                "--repository={}".format(repo_path),
                "--config-dir=../resources/etc-active",
                "--no-systemd"]) == ""

    # Check introspection to active is working right.
    active = set(check_output([
        "pkgpanda",
        "active",
        "--root={0}/root".format(tmpdir),
        "--rooted-systemd",
        "--repository={}".format(repo_path),
        "--config-dir=../resources/etc-active"]).decode().split())

    assert active == {"mesos--0.22.0", "mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8"}

    # Swap out one package
    assert run(["pkgpanda",
                "swap",
                "mesos-config--justmesos",
                "--root={0}/root".format(tmpdir),
                "--rooted-systemd",
                "--repository={}".format(repo_path),
                "--config-dir=../resources/etc-active",
                "--no-systemd"]) == ""

    # Check introspection to active is working right.
    active = set(check_output([
        "pkgpanda",
        "active",
        "--root={0}/root".format(tmpdir),
        "--rooted-systemd",
        "--repository={}".format(repo_path),
        "--config-dir=../resources/etc-active"]).decode().split())

    assert active == {"mesos--0.22.0", "mesos-config--justmesos"}

    assert run(["pkgpanda",
                "activate",
                "mesos--0.22.0",
                "--root={0}/root".format(tmpdir),
                "--rooted-systemd",
                "--repository={}".format(repo_path),
                "--config-dir=../resources/etc-active",
                "--no-systemd"]) == ""

    # Check introspection to active is working right.
    active = set(check_output([
        "pkgpanda",
        "active",
        "--root={0}/root".format(tmpdir),
        "--rooted-systemd",
        "--repository={}".format(repo_path),
        "--config-dir=../resources/etc-active"]).decode().split())

    assert active == {"mesos--0.22.0"}

    # Check that mesos--0.23.0 gets its state directory created.
    assert not os.path.isdir(str(state_dir_root) + '/mesos')
    assert run(["pkgpanda",
                "activate",
                "mesos--0.23.0",
                "--root={0}/root".format(tmpdir),
                "--rooted-systemd",
                "--repository={}".format(repo_path),
                "--config-dir=../resources/etc-active",
                "--no-systemd",
                "--state-dir-root={}".format(state_dir_root)]) == ""
    assert os.path.isdir(str(state_dir_root) + '/mesos')

    # TODO(cmaloney): expect_fs
    # TODO(cmaloney): Test a full OS setup using http://0pointer.de/blog/projects/changing-roots.html


def test_systemd_unit_files(tmpdir):
    repo_path = tmp_repository(tmpdir)
    tmpdir.join("root", "bootstrap").write("", ensure=True)

    check_call(["pkgpanda",
                "setup",
                "--root={0}/root".format(tmpdir),
                "--rooted-systemd",
                "--repository={}".format(repo_path),
                "--config-dir={}".format(resources_test_dir("etc-active")),
                "--no-systemd"
                ])

    unit_file = 'dcos-mesos-master.service'
    base_path = '{}/root/{}'.format(tmpdir, unit_file)
    wants_path = '{}/root/dcos.target.wants/{}'.format(tmpdir, unit_file)

    # The unit file is copied to the base dir and symlinked from dcos.target.wants.
    assert islink(wants_path)

    # on Windows we are using hard links, so base_path will report it is a link
    # therefore this path will be skipped on Windows
    if not is_windows:
        assert os.path.isfile(base_path) and not islink(base_path)
    assert realpath(wants_path) == os.path.abspath(base_path)
