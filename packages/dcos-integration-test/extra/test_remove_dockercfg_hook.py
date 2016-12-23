import uuid

import pytest


def test_remove_dockercfg_hook(cluster):
    """Test that the remove .dockercfg hook is working properly.

    If the hook is enabled, the test expects that the .dockercfg file
    (downloaded as a uri via the Mesos fetcher) is removed from the task's sandbox.

    """

    # Skip the test if the hook is disabled
    if not cluster.dockercfg_hook_enabled:
        return

    # Create a one-off job checking that the fetched .dockercfg file is not in the sandbox
    job = {
        'id': 'integration-test--' + uuid.uuid4().hex,
        'run': {
            'cpus': 0.1, 'mem': 32,
            'cmd': "test ! -f .dockercfg",
            'artifacts': [{'uri': "file:///opt/mesosphere/active/dcos-integration-test/.dockercfg"}]}}
    removed = cluster.metronome_one_off(job)
    assert removed, 'dockercfg was not removed from the sandbox'
