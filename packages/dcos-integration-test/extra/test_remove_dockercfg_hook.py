import uuid

import pytest


@pytest.fixture(scope='module')
def auth_cluster(cluster):
    if not cluster.dockercfg_hook_enabled:
        pytest.skip("Skipped because not running against cluster with remove .dockercfg hook.")
    return cluster


def test_remove_dockercfg_hook(cluster):
    """Test that the remove .dockercfg hook is working properly.

    If the hook is enabled, the test expects that the .dockercfg file
    (which is downloaded as a uri via the Mesos fetcher) is removed.

    """

    # Create a one-off job checking that the fetched .dockercfg file is
    # not in the sandbox
    test_uuid = uuid.uuid4().hex
    job = {
        'id': 'integration-test--' + test_uuid,
        'run': {
            'cpus': 0.1,
            'mem': 32,
            'disk': 0,
            'cmd': "test -f .dockercfg",
            'artifacts': [{
                'uri': "file:///opt/mesosphere/active/dcos-integration-test/.dockercfg"}]}}
    try:
        cluster.metronome_one_off(job)
    except Exception as ex:
        raise Exception(".dockercfg was not removed")
