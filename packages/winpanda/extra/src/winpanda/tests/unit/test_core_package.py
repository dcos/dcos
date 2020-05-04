import pytest
import mock
import unittest

from core.package.id import PackageId
from core.package.manifest import PackageManifest, IStorNodes
from core.package.package import Package


class TestPackageId(unittest.TestCase):
    """DC/OS package ID type unit tests."""

    def test_str_method_should_return_id_string(self):
        """Check PackageId __str__ magic method return value."""
        name = 'id--ver'
        pkg = PackageId(name)
        assert str(pkg) == name

    def test_wrong_id_should_fail(self):
        """Check PackageId wrong id value exception handling."""
        with pytest.raises(ValueError):
            PackageId('id')

    def test_name_and_version_should_create_id(self):
        """Check PackageId constructor pkg_name and pkg_version processing."""
        pkg = PackageId(pkg_name='id', pkg_version='ver')
        assert str(pkg) == 'id--ver'


class TestPackageManifest(unittest.TestCase):
    """Package manifest container unit tests."""

    @mock.patch('core.utils.rc_load_json', retun_value='')
    @mock.patch('core.utils.rc_load_yaml', return_value='')
    @mock.patch('core.utils.rc_load_ini', return_value='')
    def test_package_id_should_be_same_as_in_package(self, *args):
        """Check PackageManifest constructor package_id processing."""
        pkg = PackageId('id--ver')
        manifest = PackageManifest(pkg, mock.Mock(spec=IStorNodes), {})
        assert str(manifest.pkg_id) == pkg.pkg_id


class TestPackage(unittest.TestCase):
    """Package manager unit tests."""

    def test_manifest_should_not_be_changed_in_init(self, *args):
        """Check Package constructor manifest processing."""
        manifest = mock.Mock(spec=PackageManifest)
        manifest.pkg_svccfg = {}
        pack = Package(PackageId(), manifest=manifest)
        assert pack.manifest == manifest
