# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

from generic_test_code.common import generic_response_headers_verify_test


class TestLogsEndpoint:
    def test_if_xaccel_header_is_passed_to_client_by_ar(
            self,
            agent_ar_process,
            valid_user_header,
            mocker):

        accel_buff_header = {"X-Accel-Buffering": "TEST"}

        mocker.send_command(
            endpoint_id='http:///run/dcos/dcos-log.sock',
            func_name='set_response_headers',
            aux_data=accel_buff_header,
        )

        generic_response_headers_verify_test(
            agent_ar_process,
            valid_user_header,
            '/system/v1/logs/v1/foo/bar',
            assert_headers=accel_buff_header,
            )
