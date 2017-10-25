import uuid

import pytest

from test_helpers import expanded_config


@pytest.mark.skipif(expanded_config['dcos_remove_dockercfg_enable'] == 'true',
                    reason=".dockercfg hook is disabled")
def test_remove_dockercfg_hook(dcos_api_session):
    """Test that the remove .dockercfg hook is working properly.

    If the hook is enabled, the test expects that the .dockercfg file
    (downloaded as a uri via the Mesos fetcher) is removed from the task's sandbox.
    """

    # Create a one-off job checking that the fetched .dockercfg file is not in the sandbox
    job = {
        'id': 'integration-test--' + uuid.uuid4().hex,
        'run': {
            'cpus': .1,
            'mem': 32,
            'disk': 0,
            'cmd': "test ! -f .dockercfg",
            'artifacts': [{'uri': "file:///opt/mesosphere/active/dcos-integration-test/util/.dockercfg"}]}}
    dcos_api_session.metronome_one_off(job)
