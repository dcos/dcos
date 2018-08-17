import logging
import random
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


def test_checks_api(dcos_api_session):
    """Test the checks API at /system/checks/"""
    checks_uri = '/system/checks/v1/'
    # Test that we can list and run node and cluster checks on a master, agent, and public agent.
    check_nodes = []
    for nodes in [dcos_api_session.masters, dcos_api_session.slaves, dcos_api_session.public_slaves]:
        if nodes:
            check_nodes.append(random.choice(nodes))
    logging.info('Testing %s on these nodes: %s', checks_uri, ', '.join(check_nodes))

    for node in check_nodes:
        for check_type in ['node', 'cluster']:
            uri = '{}{}/'.format(checks_uri, check_type)
            logging.info('Testing %s on %s', uri, node)

            # List checks
            r = dcos_api_session.get(uri, node=node)
            assert r.status_code == 200
            checks = r.json()
            assert isinstance(checks, dict)

            # Run checks
            r = dcos_api_session.post(uri, node=node)
            assert r.status_code == 200
            results = r.json()
            assert isinstance(results, dict)
            assert results['status'] == 0

            # Make sure we ran all the listed checks.
            assert set(checks.keys()) == set(results['checks'].keys())
