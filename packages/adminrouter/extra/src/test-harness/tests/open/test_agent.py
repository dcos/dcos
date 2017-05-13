# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import logging

import pytest
import requests

from generic_test_code.common import verify_header

log = logging.getLogger(__name__)
pytestmark = pytest.mark.usefixtures("agent_ar_process")


class TestMetricsEndpointOpen:
    def test_if_request_is_sent_to_correct_upstream(self,
                                                    valid_user_header,
                                                    agent_ar_process):
        url = agent_ar_process.make_url_from_path("/system/v1/metrics/some/path")
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 200
        req_data = resp.json()
        assert req_data['endpoint_id'] == 'http:///run/dcos/dcos-metrics-agent.sock'

    def test_if_upstream_request_is_correct(self,
                                            valid_user_header,
                                            agent_ar_process):
        url = agent_ar_process.make_url_from_path("/system/v1/metrics/some/path")
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 200
        req_data = resp.json()
        assert req_data['method'] == 'GET'
        assert req_data['path'] == '/some/path'
        assert req_data['request_version'] == 'HTTP/1.0'
        verify_header(req_data['headers'], 'X-Forwarded-For', '127.0.0.1')
        verify_header(req_data['headers'], 'X-Forwarded-Proto', 'http')
        verify_header(req_data['headers'], 'X-Real-IP', '127.0.0.1')
