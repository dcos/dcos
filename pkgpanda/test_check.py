from subprocess import check_output, PIPE, Popen, STDOUT

from pkgpanda.util import resources_test_dir

list_output = """WARNING: `not_executable.py` is not executable
pkg1--12345
 - hello_world_ok.py
pkg2--12345
 - failed_check.py
 - shell_script_check.sh
"""

run_output_stdout = """Hello World
I exist to fail...
Assertion error
Hello World
"""

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
    assert stderr.decode() == run_output_stderr
    assert stdout.decode() == run_output_stdout
