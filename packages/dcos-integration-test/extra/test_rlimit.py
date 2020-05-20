import subprocess
import uuid

from dcos_test_utils.dcos_api import DcosApiSession

__maintainer__ = 'bbannier'
__contact__ = 'core-team@mesosphere.io'


def test_if_rlimits_can_be_used(dcos_api_session: DcosApiSession) -> None:
    """This test verifies that rlimits can be used.

    Since marathon does not support rlimits yet we use `mesos-execute` as
    scheduler. We run a job for which we specify an unlimited `RLIMIT_CORE`.
    The job then examines the actual limit, and returns a failure if another
    value is found."""

    name = 'test-rlimits-{}'.format(uuid.uuid4().hex)

    argv = [
        '/opt/mesosphere/bin/mesos-execute',
        '--rlimits={"rlimits": [{"type":"RLMT_CORE"}]}',
        '--master=leader.mesos:5050',
        '--name={}'.format(name),
        '--command=ulimit -c | grep -q unlimited',
        '--shell=true',
        '--env={"LC_ALL":"C"}']

    output = subprocess.check_output(
        argv,
        stderr=subprocess.STDOUT,
        universal_newlines=True)

    expected_output = \
        "Received status update TASK_FINISHED for task '{name}'".format(
            name=name)

    assert expected_output in output
