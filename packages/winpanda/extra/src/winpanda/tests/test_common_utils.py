import pytest

from common.exceptions import ExternalCommandError
from common.utils import run_external_command, transfer_files

EXPECTED_FILE_CONTENT = 'test'

_cmd_success = """$ErrorActionPreference = "stop"
Write-Output "output"
"""

_cmd_error = """$ErrorActionPreference = "stop"
Write-Output "output"
Write-Error "error"
"""

_cmd_failure = """$ErrorActionPreference = "stop"
Write-Output "output"
exit 4
"""

_cmd_slow = """$ErrorActionPreference = "stop"
Write-Output "line 1"
Start-Sleep 10
Write-Output "line 2"
"""

_cmd_verbose = """$ErrorActionPreference = "stop"
$str = "*" * 99999
Write-Output "$str"
"""


def test_run_external_command_success(tmp_path):
    """
    Output can be captured from a successful process.
    """
    script = tmp_path / 'script.ps1'
    script.write_text(_cmd_success)
    p = run_external_command(('powershell', '-executionpolicy', 'Bypass', '-File', str(script)))
    assert p.returncode == 0
    assert p.stdout.strip() == 'output'
    assert p.stderr.strip() == ''


def test_run_external_command_failure(tmp_path):
    """
    An exception is raised on a non-zero exit.
    """
    script = tmp_path / 'script.ps1'
    script.write_text(_cmd_failure)
    with pytest.raises(ExternalCommandError) as e:
        run_external_command(('powershell', '-executionpolicy', 'Bypass', '-File', str(script)))
    # no way to access returncode, stdout, and stderr
    assert 'Exit code [4]' in str(e)


def test_run_external_command_error(tmp_path):
    """
    A PowerShell script fails if text is written to error stream.
    """
    script = tmp_path / 'script.ps1'
    script.write_text(_cmd_error)
    with pytest.raises(ExternalCommandError) as e:
        run_external_command(('powershell', '-executionpolicy', 'Bypass', '-File', str(script)))
    # no way to access returncode, stdout, and stderr
    assert 'WriteErrorException' in str(e)


def test_run_external_command_slow(tmp_path):
    """
    All output is returned, even if slow.
    """
    script = tmp_path / 'script.ps1'
    script.write_text(_cmd_slow)
    p = run_external_command(('powershell', '-executionpolicy', 'Bypass', '-File', str(script)))
    assert p.returncode == 0
    assert p.stdout.strip() == 'line 1\nline 2'
    assert p.stderr.strip() == ''


def test_run_external_command_timeout(tmp_path):
    """
    A process times-out if it runs longer than expected.
    """
    script = tmp_path / 'script.ps1'
    script.write_text(_cmd_slow)
    with pytest.raises(ExternalCommandError) as e:
        run_external_command(('powershell', '-executionpolicy', 'Bypass', '-File', str(script)), 2)
    # no way to access returncode, stdout, and stderr
    assert 'timed out' in str(e)


def test_run_external_command_verbose(tmp_path):
    """
    Processes can generate large output.
    """
    script = tmp_path / 'script.ps1'
    script.write_text(_cmd_verbose)
    p = run_external_command(('powershell', '-executionpolicy', 'Bypass', '-File', str(script)))
    assert p.returncode == 0
    assert len(p.stdout.strip()) == 99999


def check_file(path):
    assert path.exists()
    with path.open() as f:
        contents = f.read()
    assert contents == EXPECTED_FILE_CONTENT


def test_transfer_files(tmp_path):
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    src.mkdir()
    dst.mkdir()
    (src / 'sub').mkdir()
    with (src / 'file1').open('w') as f:
        f.write(EXPECTED_FILE_CONTENT)
    with (src / 'sub' / 'file2').open('w') as f:
        f.write(EXPECTED_FILE_CONTENT)
    transfer_files(str(src), str(dst))
    check_file(dst / 'file1')
    check_file(dst / 'sub' / 'file2')
