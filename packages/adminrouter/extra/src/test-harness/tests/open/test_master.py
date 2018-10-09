# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import logging

import pytest
import requests

from generic_test_code.common import overridden_file_content
from mocker.endpoints.mesos import AGENT1_ID

log = logging.getLogger(__name__)

authed_endpoints = [
    '/acs/api/v1/reflect/me',
    '/capabilities',
    '/cosmos/service/foo/bar',
    '/dcos-history-service/foo/bar',
    '/exhibitor/foo/bar',
    '/marathon/v2/reflect/me',
    '/mesos/reflect/me',
    '/mesos_dns/v1/reflect/me',
    '/metadata',
    '/dcos-metadata/plain-metadata-testfile.json',
    '/navstar/lashup/key',
    '/package/foo/bar',
    '/pkgpanda/foo/bar',
    '/pkgpanda/active.buildinfo.full.json',
    '/service/scheduler-alwaysthere/foo/bar',
    '/service/nest1/scheduler-alwaysthere/foo/bar',
    '/service/nest2/nest1/scheduler-alwaysthere/foo/bar',
    '/slave/{}'.format(AGENT1_ID),
    '/system/health/v1/foo/bar',
    '/system/v1/agent/{}/logs/foo/bar'.format(AGENT1_ID),
    '/system/v1/agent/{}/metrics/v0/foo/bar'.format(AGENT1_ID),
    '/system/v1/leader/marathon/foo/bar',
    '/system/v1/leader/mesos/foo/bar',
    '/system/v1/logs/foo/bar',
    '/system/v1/metrics/foo/bar',
]


# Note(JP): this test assumes that the IAM is in the hot path for
# authorization. That should not be the case, by design.

# class TestAuthEnforcementOpen:

#     @pytest.mark.parametrize("path", authed_endpoints)
#     def test_if_unknown_user_is_forbidden_access(
#             self, mocker, master_ar_process, path, valid_user_header):
#         log_messages = {
#             'User not found: `bozydar`':
#                 SearchCriteria(1, True)}
#         with iam_denies_all_requests(mocker):
#             with assert_iam_queried_for_uid(mocker, 'bozydar'):
#                 assert_endpoint_response(
#                     master_ar_process,
#                     path,
#                     401,
#                     headers=valid_user_header,
#                     assert_stderr=log_messages)

#     @pytest.mark.parametrize("path", authed_endpoints)
#     def test_if_known_user_is_permitted_access(
#             self, mocker, master_ar_process, path, valid_user_header):

#        is_auth_location = path.startswith("/acs/api/v1")
#        with assert_iam_queried_for_uid(
#                mocker, 'bozydar', expect_two_iam_calls=is_auth_location):
#            assert_endpoint_response(
#                master_ar_process,
#                path,
#                200,
#                headers=valid_user_header,
#                )


class TestDcosMetadata:
    @pytest.mark.parametrize("uniq_content", ["(｡◕‿‿◕｡)", "plain text 1234"])
    @pytest.mark.parametrize("path", ["plain-metadata-testfile.json",
                                      "nest1/nested-metadata-testfile.json"])
    def test_if_metadata_files_are_handled(
            self,
            master_ar_process,
            valid_user_header,
            uniq_content,
            path):

        url = master_ar_process.make_url_from_path('/dcos-metadata/{}'.format(path))

        with overridden_file_content(
                '/opt/mesosphere/active/dcos-metadata/etc/{}'.format(path),
                uniq_content):
            resp = requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header)

        assert resp.status_code == 200
        resp.encoding = 'utf-8'
        assert resp.text == uniq_content
