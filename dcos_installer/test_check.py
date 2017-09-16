import pytest

from dcos_installer import check


def assert_check_runner_error(check_runner_response):
    crr = check.CheckRunnerResult(check_runner_response)
    assert crr.is_error
    assert crr.error_message == check_runner_response['error']


def assert_check_runner_result(check_runner_response):
    crr = check.CheckRunnerResult(check_runner_response)
    assert not crr.is_error
    assert crr.status == check_runner_response['status']
    assert crr.status_text == crr.statuses[crr.status]
    assert crr.checks == {
        name: check.Check(
            name=name,
            status=result['status'],
            status_text=crr.statuses[result['status']],
            output=result['output'])
        for name, result in check_runner_response['checks'].items()
    }


def test_check_runner_result():
    assert_check_runner_result({'status': 0, 'checks': {}})
    assert_check_runner_result({
        'status': 0,
        'checks': {
            'foo': {
                'status': 0,
                'output': '',
            },
            'bar': {
                'status': 0,
                'output': 'bar output',
            },
        },
    })
    assert_check_runner_error({'error': 'something failed'})

    # Assert unexpected keys and values expected in a success response raise an exception.
    with pytest.raises(Exception):
        check.CheckRunnerResult({})
    with pytest.raises(Exception):
        check.CheckRunnerResult({'status': 0})
    with pytest.raises(Exception):
        check.CheckRunnerResult({'status': 0, 'checks': []})
    with pytest.raises(Exception):
        check.CheckRunnerResult({'status': 0, 'checks': {'foo': {}}})

    # Assert missing or unexpected keys and values expected in an error response raise an exception.
    with pytest.raises(Exception):
        check.CheckRunnerResult({'error': 'Something failed.', 'status': 3})
    with pytest.raises(Exception):
        check.CheckRunnerResult({'error': 'Something failed.', 'checks': {}})
