import mock
import unittest
import pytest

from cfgm.cfgm import PkgConfManager
from cfgm import exceptions
from core.package.manifest import PackageManifest


class TestPkgConfManager(unittest.TestCase):
    """DC/OS package configuration files manager unit tests."""

    @staticmethod
    def get_manifest_mock(exists=False, is_symlink=True, is_reserved=True, is_dir=False):
        path = mock.Mock()
        path.exists.return_value = exists
        path.is_symlink.return_value = is_symlink
        path.is_reserved.return_value = is_reserved
        path.is_dir.return_value = is_dir

        manifest = mock.Mock(spec=PackageManifest)
        manifest.istor_nodes.inst_pkgrepo.joinpath.return_value = path

        return manifest

    @mock.patch('cfgm.cfgm.isinstance', return_value=True)
    def test_init_should_check_manifest_type(self, *args):
        """Check PkgConfManager __str__ magic method return value."""
        manifest_name = 'manifest_name'
        manifest = mock.MagicMock(spec=PackageManifest)
        manifest.__str__.return_value = manifest_name
        pkg_conf_manager = PkgConfManager(manifest)
        assert str(pkg_conf_manager) == f'PkgConfManager({manifest_name})'

    def test_setup_empty_manifest_should_fail(self):
        manifest = mock.Mock(spec=PackageManifest)
        cfg_manager = PkgConfManager(manifest)
        with pytest.raises(exceptions.PkgConfInvalidError):
            cfg_manager.setup_conf()

    def test_setup_symlink_should_fail(self):
        manifest_mock = self.get_manifest_mock(exists=True)
        cfg_manager = PkgConfManager(manifest_mock)
        with pytest.raises(exceptions.PkgConfInvalidError):
            cfg_manager.setup_conf()

    def test_setup_reserved_should_fail(self):
        manifest_mock = self.get_manifest_mock(exists=True, is_symlink=False)
        cfg_manager = PkgConfManager(manifest_mock)
        with pytest.raises(exceptions.PkgConfInvalidError):
            cfg_manager.setup_conf()

    def test_setup_not_dir_should_fail(self):
        manifest_mock = self.get_manifest_mock(exists=True, is_symlink=False, is_reserved=False)
        cfg_manager = PkgConfManager(manifest_mock)
        with pytest.raises(exceptions.PkgConfInvalidError):
            cfg_manager.setup_conf()
