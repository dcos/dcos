import pytest

from pkgpanda.util import expect_fs, is_windows, resources_test_dir, run

fetch_output = """\rFetching: mesos--0.22.0\rFetched: mesos--0.22.0\n"""


@pytest.mark.skipif(is_windows, reason="test fails on Windows reason unknown")
def test_fetch(tmpdir):
    # NOTE: tmpdir is explicitly empty because we want to be sure a fetch.
    # succeeds when there isn't anything yet.
    # Start a simpleHTTPServer to serve the packages
    # fetch a couple packages
    assert run([
               "pkgpanda",
               "fetch",
               "mesos--0.22.0",
               "--repository={0}".format(tmpdir),
               "--repository-url=file://{}/".format(resources_test_dir('remote_repo'))
               ]) == fetch_output

    # Ensure that the package at least somewhat extracted correctly.
    expect_fs(
        "{0}".format(tmpdir),
        {
            "mesos--0.22.0": ["lib", "bin_master", "bin_slave", "pkginfo.json", "bin"]
        })
    # TODO(cmaloney): Test multiple fetches on one line.
    # TODO(cmaloney): Test unable to fetch case.


@pytest.mark.skipif(is_windows, reason="test fails on Windows reason unknown")
def test_add(tmpdir):
    assert run([
               "pkgpanda",
               "add",
               resources_test_dir('remote_repo/packages/mesos/mesos--0.22.0.tar.xz'),
               "--repository={0}".format(tmpdir),
               ]) == ""

    # Ensure that the package at least somewhat extracted correctly.
    expect_fs(
        "{0}".format(tmpdir),
        {
            "mesos--0.22.0": ["lib", "bin_master", "bin_slave", "pkginfo.json", "bin"]
        })
    # TODO(branden): Test unable to add case.
