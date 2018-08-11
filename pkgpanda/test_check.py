from subprocess import check_output, PIPE, Popen, STDOUT

from pkgpanda.util import is_windows, resources_test_dir

if is_windows:
    # File permissions are different on Windows, as well as end of line characters
    list_output = """pkg1--12345\r
 - hello_world_ok.py\r
 - not_executable.py\r
pkg2--12345\r
 - failed_check.py\r
 - shell_script_check.ps1\r
"""
else:
    list_output = """WARNING: `not_executable.py` is not executable
pkg1--12345
 - hello_world_ok.py
pkg2--12345
 - failed_check.py
 - shell_script_check.sh
"""

if is_windows:
    run_output_stdout = """Hello World\r
I exist to fail...\r
Assertion error\r
Hello World\r
"""
else:
    run_output_stdout = """Hello World
I exist to fail...
Assertion error
Hello World
"""

if is_windows:
    # execution permission is not used on Windows so this error does not happen
    run_output_stderr = ""
else:
    run_output_stderr = """WARNING: `not_executable.py` is not executable
"""


def test_check_target_list():
    output = check_output([
        'pkgpanda',
        'check',
        '--list',
        '--root', resources_test_dir("opt/mesosphere"),
        '--repository', resources_test_dir("opt/mesosphere/packages")], stderr=STDOUT)
    assert output.decode() == list_output


def test_check_target_run():
    cmd = Popen([
        'pkgpanda',
        'check',
        '--root', resources_test_dir('opt/mesosphere'),
        '--repository', resources_test_dir('opt/mesosphere/packages')],
        stdout=PIPE, stderr=PIPE)
    stdout, stderr = cmd.communicate()
    assert stdout.decode() == run_output_stdout
    assert stderr.decode() == run_output_stderr
