import logging
import uuid

import pytest


def test_remove_dockercfg_hook(dcos_api_session):
    """Test that the remove .dockercfg hook is working properly.

    If the hook is enabled, the test expects that the .dockercfg file
    (downloaded as a uri via the Mesos fetcher) is removed from the task's sandbox.

    """

    # Skip the test if the hook is disabled
    if not dcos_api_session.dockercfg_hook_enabled:
        pytest.skip('Test requires dockercfg hook to be enabled')

    # Create a one-off job checking that the fetched .dockercfg file is not in the sandbox
    job = {
        'id': 'integration-test--' + uuid.uuid4().hex,
        'run': {
            'cpus': .1,
            'mem': 32,
            'disk': 0,
            'cmd': "test ! -f .dockercfg",
            'artifacts': [{'uri': "file:///opt/mesosphere/active/dcos-integration-test/.dockercfg"}]}}
    removed = dcos_api_session.metronome_one_off(job)
    assert removed, 'dockercfg was not removed from the sandbox'
    logging.info('Completed test: dockercfg was successfully removed')
