# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import pytest
import requests

from generic_test_code.common import generic_verify_response_test


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

        generic_verify_response_test(
            agent_ar_process,
            valid_user_header,
            '/system/v1/logs/foo/bar',
            assert_headers=accel_buff_header,
            )


class TestAgentMisc:
    @pytest.mark.parametrize('path', ['/', '/foo', '/foo/bar'])
    def test_if_document_root_is_not_served_by_the_agent_ar(
            self,
            agent_ar_process,
            valid_user_header,
            path):

        url = agent_ar_process.make_url_from_path(path)
        resp = requests.get(
            url,
            allow_redirects=False,
            headers=valid_user_header
            )

        assert resp.status_code == 404
