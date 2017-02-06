import subprocess
import uuid


def test_if_default_systctls_are_set(dcos_api_session):
    """This test verifies that default sysctls are set for tasks.

    We use a `mesos-execute` to check for the values to make sure any task from
    any framework would be affected by default.
    The job then examines the default sysctls, and returns a failure if another
    value is found."""

    test_command = ('test "$(/usr/sbin/sysctl vm.swappiness)" = '
                    '"vm.swappiness = 1"'
                    ' && test "$(/usr/sbin/sysctl vm.max_map_count)" = '
                    '"vm.max_map_count = 262144"')

    argv = [
        '/opt/mesosphere/bin/mesos-execute',
        '--master=leader.mesos:5050',
        '--command={}'.format(test_command),
        '--shell=true',
        '--env={"LC_ALL":"C"}']

    def run_and_check(argv):
        name = 'test-sysctl-{}'.format(uuid.uuid4().hex)
        output = subprocess.check_output(
            argv + ['--name={}'.format(name)],
            stderr=subprocess.STDOUT,
            universal_newlines=True)

        expected_output = \
            "Received status update TASK_FINISHED for task '{name}'".format(
                name=name)

        assert expected_output in output

    run_and_check(argv)
    run_and_check(argv + ['--role=slave_public'])
