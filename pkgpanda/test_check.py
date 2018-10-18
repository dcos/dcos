from subprocess import PIPE, Popen

from pkgpanda.util import is_windows, resources_test_dir


package_dir = "packages"

if is_windows:
    package_script = "shell_script_check.ps1"
    output_stderr = "WARNING: `not_supported.dummy` file-type is not supported\n"
else:
    package_script = "shell_script_check.sh"
    output_stderr = "WARNING: `not_executable.py` is not executable\n"

list_output_stdout = """pkg1--12345
 - hello_world_ok.py
pkg2--12345
 - failed_check.py
 - {}
""".format(package_script)

run_output_stdout = """Hello World
I exist to fail...
Assertion error
Hello World
"""


def test_check_target_list():
    cmd = Popen([
        'pkgpanda',
        'check',
        '--list',
        '--root', resources_test_dir("opt/mesosphere"),
        '--repository', resources_test_dir("opt/mesosphere/{}".format(package_dir))],
        universal_newlines=True,
        stdout=PIPE, stderr=PIPE)
    stdout, stderr = cmd.communicate()
    assert stdout == list_output_stdout
    assert stderr == output_stderr


def test_check_target_run():
    cmd = Popen([
        'pkgpanda',
        'check',
        '--root', resources_test_dir('opt/mesosphere'),
        '--repository', resources_test_dir('opt/mesosphere/{}'.format(package_dir))],
        universal_newlines=True,
        stdout=PIPE, stderr=PIPE)
    stdout, stderr = cmd.communicate()
    assert stdout == run_output_stdout
    assert stderr == output_stderr
