# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import copy

import pytest

from generic_test_code.common import (
    generic_correct_upstream_dest_test,
    generic_correct_upstream_request_test,
    generic_no_slash_redirect_test,
    generic_upstream_headers_verify_test,
)

pytestmark = pytest.mark.usefixtures("agent_ar_process")


class TestLogsEndpoint:
    def test_redirect_req_without_slash(self, agent_ar_process):
        generic_no_slash_redirect_test(agent_ar_process, '/system/v1/logs/v1')

    def test_if_request_is_sent_to_correct_upstream(self,
                                                    agent_ar_process,
                                                    valid_user_header):

        generic_correct_upstream_dest_test(agent_ar_process,
                                           valid_user_header,
                                           '/system/v1/logs/v1/foo/bar',
                                           'http:///run/dcos/dcos-log.sock',
                                           )

    @pytest.mark.parametrize("path_given,path_expected",
                             [("/system/v1/logs/v1/foo/bar", "/foo/bar"),
                              ("/system/v1/logs/v1/", "/"),
                              ])
    def test_if_upstream_request_is_correct(self,
                                            agent_ar_process,
                                            valid_user_header,
                                            path_given,
                                            path_expected):

        generic_correct_upstream_request_test(agent_ar_process,
                                              valid_user_header,
                                              path_given,
                                              path_expected,
                                              http_ver="HTTP/1.1"
                                              )

    def test_if_upstream_headers_are_correct(self,
                                             agent_ar_process,
                                             valid_user_header):

        accel_buff_header = {"X-Accel-Buffering": "TEST"}

        req_headers = copy.deepcopy(valid_user_header)
        req_headers.update(accel_buff_header)

        generic_upstream_headers_verify_test(agent_ar_process,
                                             req_headers,
                                             '/system/v1/logs/v1/foo/bar',
                                             assert_headers=accel_buff_header,
                                             )
