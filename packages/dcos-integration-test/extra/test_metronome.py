__maintainer__ = 'ichernetsky'
__contact__ = 'marathon-team@mesosphere.io'


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
    j = dcos_api_session.jobs.create(job)
    job_id = j['id']
    success, _run, _job = dcos_api_session.jobs.run(job_id)
    assert success
