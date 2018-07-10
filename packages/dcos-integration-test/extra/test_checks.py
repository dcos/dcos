import uuid


__maintainer__ = 'branden'
__contact__ = 'dcos-cluster-ops@mesosphere.io'


def test_checks_cli(dcos_api_session):
    base_cmd = [
        '/opt/mesosphere/bin/dcos-shell',
        'dcos-check-runner',
        'check',
    ]
    test_uuid = uuid.uuid4().hex

    # Poststart node checks should pass.
    dcos_api_session.metronome_one_off({
        'id': 'test-checks-node-poststart-' + test_uuid,
        'run': {
            'cpus': .1,
            'mem': 128,
            'disk': 0,
            'cmd': ' '.join(base_cmd + ['node-poststart']),
        },
    })

    # Cluster checks should pass.
    dcos_api_session.metronome_one_off({
        'id': 'test-checks-cluster-' + test_uuid,
        'run': {
            'cpus': .1,
            'mem': 128,
            'disk': 0,
            'cmd': ' '.join(base_cmd + ['cluster']),
        },
    })

    # Check runner should only use the PATH and LD_LIBRARY_PATH from check config.
    dcos_api_session.metronome_one_off({
        'id': 'test-checks-env-' + test_uuid,
        'run': {
            'cpus': .1,
            'mem': 128,
            'disk': 0,
            'cmd': ' '.join([
                'env',
                'PATH=badvalue',
                'LD_LIBRARY_PATH=badvalue',
                '/opt/mesosphere/bin/dcos-check-runner',
                'check',
                'node-poststart',
            ]),
        },
    })
