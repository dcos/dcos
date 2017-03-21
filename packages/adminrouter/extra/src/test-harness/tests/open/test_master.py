# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import logging
import pytest

from generic_test_code.common import (
    assert_endpoint_response,
    generic_correct_upstream_dest_test,
)
from generic_test_code.open import assert_iam_queried_for_uid
from util import SearchCriteria, iam_denies_all_requests

log = logging.getLogger(__name__)

authed_endpoints = [
    '/acs/api/v1/foo/bar',
    '/capabilities',
    '/cosmos/service/foo/bar',
    '/dcos-history-service/foo/bar',
    '/exhibitor/foo/bar',
    '/marathon/v2/apps',
    '/mesos/master/state-summary',
    '/mesos_dns/foo/bar',
    '/metadata',
    '/navstar/lashup/key',
    '/package/foo/bar',
    '/pkgpanda/active.buildinfo.full.json',
    '/service/nginx-alwaysthere/foo/bar',
    '/service/nginx-alwaysthere/foo/bar',
    '/slave/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1',
    '/system/health/v1/foo/bar',
    '/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1/logs/v1/foo/bar',
    '/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1/metrics/v0/foo/bar',
    '/system/v1/leader/marathon/foo/bar',
    '/system/v1/leader/mesos/foo/bar',
    '/system/v1/logs/v1/foo/bar',
    '/system/v1/metrics/foo/bar',
]


class TestAuthEnforcementOpen:
    @pytest.mark.parametrize("path", authed_endpoints)
    def test_if_unknown_user_is_forbidden_access(
            self, mocker, master_ar_process, path, valid_user_header):
        log_messages = {
            'validate_jwt_or_exit\(\): User not found: `bozydar`':
                SearchCriteria(1, True)}
        with iam_denies_all_requests(mocker):
            with assert_iam_queried_for_uid(mocker, 'bozydar'):
                assert_endpoint_response(
                    master_ar_process,
                    path,
                    401,
                    headers=valid_user_header,
                    assert_stderr=log_messages)

    @pytest.mark.parametrize("path", authed_endpoints)
    def test_if_known_user_is_permitted_access(
            self, mocker, master_ar_process, path, valid_user_header):

        is_auth_location = path.startswith("/acs/api/v1")
        with assert_iam_queried_for_uid(
                mocker, 'bozydar', expect_two_iam_calls=is_auth_location):
            assert_endpoint_response(
                master_ar_process,
                path,
                200,
                headers=valid_user_header,
                )


class TestHealthEndpointOpen:
    def test_if_request_is_sent_to_correct_upstream(self,
                                                    master_ar_process,
                                                    valid_user_header):

        generic_correct_upstream_dest_test(master_ar_process,
                                           valid_user_header,
                                           '/system/health/v1/foo/bar',
                                           'http://127.0.0.1:1050',
                                           )
