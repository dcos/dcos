from shutil import copytree
from subprocess import check_call, check_output

from pkgpanda.util import expect_fs, run


def tmp_repository(temp_dir, repo_dir="../resources/packages"):
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
                "--config-dir=../resources/etc-active",
                "--no-systemd"
                ])
    # TODO(cmaloney): Validate things got placed correctly.

    expect_fs(
        "{0}/root".format(tmpdir),
        {
            "active": ["env", "mesos", "mesos-config"],
            "active.buildinfo.full.json": None,
            "bin": [
                "mesos",
                "mesos-dir",
                "mesos-master",
                "mesos-slave"],
            "lib": ["libmesos.so"],
            "etc": ["foobar", "some.json"],
            "include": [],
            "dcos.target.wants": [],
            "dcos.target": None,
            "environment": None,
            "environment.export": None
        })

    # Introspection should work right
    active = set(check_output([
        "pkgpanda",
        "active",
        "--root={0}/root".format(tmpdir),
        "--rooted-systemd",
        "--repository={}".format(repo_path),
        "--config-dir=../resources/etc-active"
        ]).decode("utf-8").split())

    assert active == {"env--setup", "mesos--0.22.0", "mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8"}
    tmpdir.join("root", "bootstrap").write("", ensure=True)
    # If we setup the same directory again we should get .old files.
    check_call(["pkgpanda",
                "setup",
                "--root={0}/root".format(tmpdir),
                "--rooted-systemd",
                "--repository={}".format(repo_path),
                "--config-dir=../resources/etc-active",
                "--no-systemd"
                ])
    # TODO(cmaloney): Validate things got placed correctly.

    expect_fs(
        "{0}/root".format(tmpdir),
        {
            "active": ["env", "mesos", "mesos-config"],
            "active.buildinfo.full.json.old": None,
            "active.buildinfo.full.json": None,
            "bin": [
                "mesos",
                "mesos-dir",
                "mesos-master",
                "mesos-slave"],
            "lib": ["libmesos.so"],
            "etc": ["foobar", "some.json"],
            "include": [],
            "dcos.target": None,
            "dcos.target.wants": [],
            "environment": None,
            "environment.export": None,
            "active.old": ["env", "mesos", "mesos-config"],
            "bin.old": [
                "mesos",
                "mesos-dir",
                "mesos-master",
                "mesos-slave"],
            "lib.old": ["libmesos.so"],
            "etc.old": ["foobar", "some.json"],
            "include.old": [],
            "dcos.target.wants.old": [],
            "environment.old": None,
            "environment.export.old": None
        })

    # Should only pickup the packages once / one active set.
    active = set(check_output([
        "pkgpanda",
        "active",
        "--root={0}/root".format(tmpdir),
        "--rooted-systemd",
        "--repository={}".format(repo_path),
        "--config-dir=../resources/etc-active"
        ]).decode('utf-8').split())

    assert active == {"env--setup", "mesos--0.22.0", "mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8"}

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
                "--config-dir=../resources/etc-active",
                "--no-systemd"
                ])

    expect_fs("{0}".format(tmpdir), {"repository": None})


def test_activate(tmpdir):
    repo_path = tmp_repository(tmpdir)
    tmpdir.join("root", "bootstrap").write("", ensure=True)
    # TODO(cmaloney): Depending on setup here is less than ideal, but meh.
    check_call(["pkgpanda",
                "setup",
                "--root={0}/root".format(tmpdir),
                "--rooted-systemd",
                "--repository={}".format(repo_path),
                "--config-dir=../resources/etc-active",
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
        "--config-dir=../resources/etc-active"
        ]).decode('utf-8').split())

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
        "--config-dir=../resources/etc-active"
        ]).decode('utf-8').split())

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
        "--config-dir=../resources/etc-active"
        ]).decode('utf-8').split())

    assert active == {"mesos--0.22.0"}

    # TODO(cmaloney): expect_fs
    # TODO(cmaloney): Test a full OS setup using http://0pointer.de/blog/projects/changing-roots.html
