# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import copy

import pytest

from generic_test_code.common import generic_upstream_headers_verify_test

pytestmark = pytest.mark.usefixtures("agent_ar_process")


class TestLogsEndpoint:
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
