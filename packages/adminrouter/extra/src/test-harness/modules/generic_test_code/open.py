# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

from contextlib import contextmanager


@contextmanager
def assert_iam_queried_for_uid(mocker, uid, expect_two_iam_calls=False):
    """Asserts that IAM mock has been queried for given UID

    Arguments:
        mocker (Mocker): Mocker instance with all server mocks
        uid (str): User ID that should have been queried
        expect_two_iam_calls (bool): specifies whether the request is being made to IAM
            or not. Requests being made to IAM end up in two recorded requests:
            one for IAM itself and one for policyquery.
    """
    mocker.send_command(
        endpoint_id='http://127.0.0.1:8101',
        func_name='record_requests',
        )

    yield

    upstream_requests = mocker.send_command(
        endpoint_id='http://127.0.0.1:8101',
        func_name='get_recorded_requests',
        )

    if not expect_two_iam_calls:
        assert len(upstream_requests) == 1
    else:
        assert len(upstream_requests) == 2
    assert upstream_requests[0]['path'] == '/acs/api/v1/users/{}'.format(uid)
    assert upstream_requests[0]['method'] == 'GET'
    assert upstream_requests[0]['request_version'] == 'HTTP/1.0'
