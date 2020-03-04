import pytest
import unittest
import mock

from common.storage import InstallationStorage
from core.exceptions import RCRemoveError, RCError, InstallationStorageError


class TestInstallationStorage(unittest.TestCase):

    @mock.patch('common.storage.Path.is_absolute', return_value=True)
    @mock.patch('common.storage.Path.mkdir')
    def test_construct_should_mkdir(self, mock_mkdir, *args):
        storage = InstallationStorage()
        storage.construct()
        mock_mkdir.assert_called_with(exist_ok=True, parents=True)

    @mock.patch('common.storage.Path.is_absolute', return_value=True)
    @mock.patch('common.storage.Path.is_dir', return_value=True)
    @mock.patch('common.storage.Path.is_file', return_value=True)
    @mock.patch('common.utils.rmdir', side_effect=OSError)
    def test_destruct_rmdir_should_fail(self, *args):
        storage = InstallationStorage()
        with pytest.raises(InstallationStorageError):
            storage.destruct()

    @mock.patch('common.storage.Path.is_absolute', return_value=True)
    @mock.patch('common.storage.Path.is_dir', return_value=True)
    @mock.patch('common.storage.Path.is_file', return_value=True)
    @mock.patch('common.utils.rmdir')
    def test_destruct_should_call_rm_dir(self, rmdir_mock, *args):
        storage = InstallationStorage()
        storage.destruct()
        rmdir_mock.assert_called()

    @mock.patch('common.storage.Path.is_absolute', return_value=True)
    @mock.patch('common.storage.Path.is_file', return_value=True)
    @mock.patch('common.storage.Path.glob', side_effect=(['test_me'], ))
    def test_get_pkgactive_should_call_loader(self, *args):
        storage = InstallationStorage()
        mock_loader = mock.Mock()
        storage.get_pkgactive(mock_loader)
        mock_loader.assert_called_once_with('test_me')

    @mock.patch('common.storage.Path.is_absolute', return_value=True)
    @mock.patch('common.utils.rmdir')
    def test_remove_package_should_remove_dir(self, mock_rmdir, *args):
        storage = InstallationStorage()
        mock_pkg = mock.Mock()
        mock_pkg.pkg_id = 'test'
        storage.remove_package(mock_pkg)
        mock_rmdir.assert_called_once()

    @mock.patch('common.storage.Path.is_absolute', return_value=True)
    @mock.patch('common.utils.rmdir', side_effect=OSError)
    def test_remove_package_error_should_fail(self, mock_rmdir, *args):
        storage = InstallationStorage()
        mock_pkg = mock.Mock()
        mock_pkg.pkg_id = 'test'
        with pytest.raises(RCRemoveError):
            storage.remove_package(mock_pkg)
