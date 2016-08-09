from shutil import copytree

from pkgpanda.util import run


list_output = """mesos:
  0.22.0
  0.23.0
mesos-config:
  ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8
  justmesos
"""

active_output = """mesos--0.22.0
mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8
"""

list_remove_output = """mesos--0.23.0
mesos-config:
  ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8
  justmesos
"""


def test_list():
    assert run(["pkgpanda", "list", "--repository=../resources/packages"]) == list_output


def test_active():
    assert run(["pkgpanda", "active", "--root=../resources/install"]) == active_output


def test_remove(tmpdir):
    repo_dir = str(tmpdir.join("repo"))
    copytree("../resources/packages", repo_dir)
    assert run([
        "pkgpanda",
        "remove",
        "mesos--0.22.0",
        "--repository={}".format(repo_dir),
        "--root=../resources/install_empty"])

    assert run(["pkgpanda", "list", "--repository={}".format(repo_dir)]) == list_remove_output
    # TODO(cmaloney): Test removing a non-existant package.
    # TODO(cmaloney): Test removing an active package.
