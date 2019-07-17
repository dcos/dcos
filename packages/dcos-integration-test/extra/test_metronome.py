import pytest

__maintainer__ = 'alenkacz'
__contact__ = 'orchestration-team@mesosphere.io'

# Apply fixture(s) in this list to all tests in this module.
# From pytest docs: "Note that the assigned variable must be called pytestmark"
pytestmark = [pytest.mark.usefixtures("clean_marathon_state")]


def test_metronome(dcos_api_session):
    job = {
        'description': 'Test Metronome API regressions',
        'id': 'test.metronome',
        'run': {
            'cmd': 'ls',
            'docker': {'image': 'busybox:latest'},
            'cpus': 1,
            'mem': 512,
            'disk': 0,
            'user': 'nobody',
            'restart': {'policy': 'ON_FAILURE'}
        }
    }
    dcos_api_session.metronome_one_off(job)
