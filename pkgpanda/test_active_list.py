from shutil import copytree

from pkgpanda.util import is_windows, resources_test_dir, run


if is_windows:
    list_output = """mesos:\r
  0.22.0\r
  0.23.0\r
mesos-config:\r
  ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8\r
  justmesos\r
"""
else:
    list_output = """mesos:
  0.22.0
  0.23.0
mesos-config:
  ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8
  justmesos
"""
if is_windows:
    active_output = """mesos--0.22.0\r
mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8\r
"""
else:
    active_output = """mesos--0.22.0
mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8
"""

if is_windows:
    list_remove_output = """mesos--0.23.0\r
mesos-config:\r
  ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8\r
  justmesos\r
"""
else:
        list_remove_output = """mesos--0.23.0
mesos-config:
  ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8
  justmesos
"""


def test_list():
    assert run(["pkgpanda", "list", "--repository={}".format(resources_test_dir("packages"))]) == list_output


def test_active():
    assert run(["pkgpanda", "active", "--root={}".format(resources_test_dir("install"))]) == active_output


def test_remove(tmpdir):
    repo_dir = str(tmpdir.join("repo"))
    copytree(resources_test_dir("packages"), repo_dir)
    assert run([
        "pkgpanda",
        "remove",
        "mesos--0.22.0",
        "--repository={}".format(repo_dir),
        "--root={}".format(resources_test_dir("install_empty"))])

    assert run(["pkgpanda", "list", "--repository={}".format(repo_dir)]) == list_remove_output
    # TODO(cmaloney): Test removing a non-existant package.
    # TODO(cmaloney): Test removing an active package.
