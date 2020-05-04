import mock
import pytest
import unittest

from extm.extm import PkgInstExtrasManager, EXTCFG_SECTION, EXTCFG_OPTION
from extm import exceptions
from subprocess import SubprocessError
from core.package.manifest import PackageManifest, IStorNodes


class TestPkgInstExtrasManager(unittest.TestCase):

    @staticmethod
    def generate_mock_manifest(cfg):
        """Generate Mock manifest based on provided configuration"""
        manifest = mock.Mock(PackageManifest)
        manifest.pkg_id.pkg_id = 'id--ver'
        manifest.pkg_extcfg = cfg
        return manifest

    def test_to_string_should_convert_manifest_configuration(self):
        """Create package extra installation options manager."""
        manifest = self.generate_mock_manifest(cfg={
            'opt': 'val'
        })
        ext_manager = PkgInstExtrasManager(manifest)
        assert str(ext_manager) == '{\'ext_conf\': {\'opt\': \'val\'}}'

    def test_wrong_install_section_should_fail(self):
        """Create package extra installation options manager with wrong install section."""
        manifest = self.generate_mock_manifest(cfg={
            EXTCFG_SECTION.INSTALL: ''
        })
        ext_manager = PkgInstExtrasManager(manifest)
        with pytest.raises(exceptions.InstExtrasManagerConfigError):
            ext_manager.handle_install_extras()

    def test_wrong_install_extras_section_should_fail(self):
        """Create package extra installation options manager with wrong extras configuration section."""
        manifest = self.generate_mock_manifest(cfg={
            EXTCFG_SECTION.INSTALL: {
                EXTCFG_OPTION.EXEC_EXT_CMD: '',
            }
        })
        ext_manager = PkgInstExtrasManager(manifest)
        with pytest.raises(exceptions.InstExtrasManagerConfigError):
            ext_manager.handle_install_extras()

    @mock.patch('subprocess.run', side_effect=SubprocessError)
    def test_install_subprocess_error_should_fail(self, *args):
        """Raise exception during installation process command execution."""
        manifest = self.generate_mock_manifest(cfg={
            EXTCFG_SECTION.INSTALL: {
                EXTCFG_OPTION.EXEC_EXT_CMD: ['command'],
            }
        })
        ext_manager = PkgInstExtrasManager(manifest)
        with pytest.raises(exceptions.InstExtrasManagerError):
            ext_manager.handle_install_extras()

    def test_wrong_uninstall_section_should_fail(self):
        """Create package extra uninstallation options manager with wrong unistall section."""
        manifest = self.generate_mock_manifest(cfg={
            EXTCFG_SECTION.UNINSTALL: ''
        })
        ext_manager = PkgInstExtrasManager(manifest)
        with pytest.raises(exceptions.InstExtrasManagerConfigError):
            ext_manager.handle_uninstall_extras()

    def test_wrong_uninstall_extras_section_should_fail(self):
        """Create package extra uninstallation options manager with wrong extras configuration section."""
        manifest = self.generate_mock_manifest(cfg={
            EXTCFG_SECTION.UNINSTALL: {
                EXTCFG_OPTION.EXEC_EXT_CMD: '',
            }
        })
        ext_manager = PkgInstExtrasManager(manifest)
        with pytest.raises(exceptions.InstExtrasManagerConfigError):
            ext_manager.handle_uninstall_extras()

    @mock.patch('subprocess.run', side_effect=SubprocessError)
    def test_uninstall_subprocess_error_should_fail(self, *args):
        """Raise exception during installation process command execution."""
        manifest = self.generate_mock_manifest(cfg={
            EXTCFG_SECTION.UNINSTALL: {
                EXTCFG_OPTION.EXEC_EXT_CMD: ['command'],
            }
        })
        ext_manager = PkgInstExtrasManager(manifest)
        with pytest.raises(exceptions.InstExtrasManagerError):
            ext_manager.handle_uninstall_extras()

    @mock.patch('subprocess.run', return_value='cmd output')
    def test_install_should_call_subprocess_run(self, mock_subprocess):
        """Raise exception during installation process command execution."""
        manifest = self.generate_mock_manifest(cfg={
            EXTCFG_SECTION.INSTALL: {
                EXTCFG_OPTION.EXEC_EXT_CMD: ['command'],
            }
        })
        ext_manager = PkgInstExtrasManager(manifest)
        ext_manager.handle_install_extras()
        mock_subprocess.assert_called_with(
            'command',
            check=True,
            stderr=-1,
            stdout=-1,
            timeout=90,
            universal_newlines=True)
