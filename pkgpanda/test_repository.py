"""Test functionality of the local package repository"""

import pytest

import pkgpanda.exceptions
from pkgpanda import Repository

from pkgpanda.util import is_windows, resources_test_dir


@pytest.fixture
def repository():
    return Repository(resources_test_dir("packages"))


@pytest.mark.skipif(is_windows, reason="test fails on Windows reason unknown")
def test_list(repository):
    packages = repository.list()
    assert type(packages) is set
    assert packages == {'mesos-config--ffddcfb53168d42f92e4771c6f8a8a9a818fd6b8',
                        'mesos--0.22.0',
                        'mesos--0.23.0',
                        'mesos-config--justmesos'}


def test_load_bad(repository):
    with pytest.raises(pkgpanda.exceptions.ValidationError):
        repository.load_packages(["invalid-package"])


def test_load_nonexistant(repository):
    with pytest.raises(pkgpanda.exceptions.PackageError):
        repository.load_packages(["missing-package--42"])
