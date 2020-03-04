import pytest
import mock
import os

from common import utils
from common.exceptions import ExternalCommandError
from subprocess import SubprocessError, CalledProcessError


@mock.patch('common.utils.SmartDL')
def test_download_should_return_destination_location(patch_smart_dl):
    """Download fake content and save it into file."""
    patch_smart_dl().get_dest.return_value = os.getcwd()
    path = utils.download('', '')
    assert path == os.getcwd()


@mock.patch('os.path.exists', return_value=False)
@mock.patch('os.mkdir')
def test_unpack_unavailable_tar_path_should_fail(*args):
    """Unpack wrong tarfile path."""
    with pytest.raises(ValueError):
        utils.unpack('', '')


@mock.patch('tarfile.open')
@mock.patch('os.path.exists', return_value=True)
def test_unpack_should_return_destination_location(mock_tar, *args):
    """Check is unpack file result provide valid location."""
    mock_tar.__enter__.return_value = mock.Mock()
    location = utils.unpack('', os.getcwd())
    assert location == os.getcwd()


@mock.patch('common.utils.Path.exists', return_value=False)
def test_rm_nonexistent_dir_should_fail(*args):
    """Remove empty path without exceptions and None result."""
    assert utils.rmdir('path') is None


@mock.patch('common.utils.Path.exists', return_value=True)
@mock.patch('common.utils.Path.is_symlink', return_value=True)
def test_rm_symlink_should_fail(*args):
    """Try remove symlink and raise exception."""
    with pytest.raises(OSError):
        utils.rmdir('/tmp/.000')


@mock.patch('common.utils.Path.exists', return_value=True)
@mock.patch('common.utils.Path.is_symlink', return_value=False)
@mock.patch('common.utils.Path.is_reserved', return_value=True)
def test_rm_reserved_should_fail(*args):
    """Try remove reserved path and raise exception."""
    with pytest.raises(OSError):
        utils.rmdir('/tmp/.000')


@mock.patch('common.utils.Path.exists', return_value=True)
@mock.patch('common.utils.Path.is_symlink', return_value=False)
@mock.patch('common.utils.Path.is_reserved', return_value=False)
@mock.patch('common.utils.Path.is_dir', return_value=False)
def test_rm_not_dir_should_fail(*args):
    """Try remove file and raise exception."""
    with pytest.raises(OSError):
        utils.rmdir('/tmp/.000')


def test_run_external_command_process_error_should_fail():
    """Check external command execution CalledProcessError handling."""
    def run(*args, **kwargs):
        # TODO need to be checked on Exception without output and stderr params
        raise CalledProcessError(1, 'command', 'out', 'err')

    with mock.patch('subprocess.run', side_effect=run):
        with pytest.raises(ExternalCommandError):
            utils.run_external_command('')


@mock.patch('subprocess.run', side_effect=SubprocessError)
def test_run_external_command_subprocess_error_should_fail(*args):
    """Check external command execution SubprocessError handling."""
    with pytest.raises(ExternalCommandError):
        utils.run_external_command('')


@mock.patch('subprocess.run', side_effect=OSError)
def test_run_external_command_os_error_should_fail(*args):
    """Check external command execution OSError handling."""
    with pytest.raises(ExternalCommandError):
        utils.run_external_command('')


@mock.patch('subprocess.run', return_value='output')
def test_successful_run_external_command_should_provide_output(mock_subprocess):
    """Check do we have external command execution output in function result and subprocess params."""
    assert utils.run_external_command('some command') == 'output'
    mock_subprocess.assert_called_once_with(
        'some command',
        check=True,
        stderr=-1,
        stdout=-1,
        timeout=30,
        universal_newlines=True)


@pytest.mark.parametrize("x,y", [(1, 1), (1, 10), (3, 4)])
def test_get_retry_interval_should_be_in_range(x, y):
    """Function retry_interval execution output needs to be between assigned interval."""
    val = utils.get_retry_interval(1, x, y)

    assert val >= x
    assert val <= y


@mock.patch('time.sleep')
def test_retry_on_exc_attempts_should_be_as_setup(mock_sleep):
    @utils.retry_on_exc((Exception,), max_attempts=2)
    def test():
        raise Exception()

    with pytest.raises(Exception):
        test()

    assert mock_sleep.call_count == 2


def test_retry_on_exc_should_return():
    @utils.retry_on_exc()
    def test():
        return 'ok'

    assert test() == 'ok'


@mock.patch('os.mkdir')
@mock.patch('os.link')
@mock.patch('os.listdir', side_effect=[['one'], ['two']])
@mock.patch('os.path.isdir', side_effect=[True, False, False])
def test_transfer_files_should_call_mkdir_and_link(mock_mkdir, mock_link, *args):
    """Check transfer files in to new directory mkdir and link invocation."""
    utils.transfer_files('/tmp/.000', '/tmp/.001')
    # Mocked file names not specified because of OS different directory separators
    assert mock_mkdir.called
    assert mock_link.called
