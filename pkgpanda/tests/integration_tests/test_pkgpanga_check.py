from subprocess import check_output, PIPE, Popen, STDOUT


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
    output = check_output('pkgpanda check --list --root ../resources/opt/mesosphere'
                          ' --repository ../resources/opt/mesosphere/packages',
                          stderr=STDOUT, shell=True)
    assert output.decode('UTF-8') == list_output


def test_check_target_run():
    cmd = Popen('pkgpanda check --root ../resources/opt/mesosphere'
                ' --repository ../resources/opt/mesosphere/packages',
                stdout=PIPE, stderr=PIPE, shell=True)
    stdout, stderr = cmd.communicate()
    assert stdout.decode('UTF-8') == run_output_stdout
    assert stderr.decode('UTF-8') == run_output_stderr
