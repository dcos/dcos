# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import copy
import logging
import os
import time

import pytest
import requests

from generic_test_code.common import (
    generic_correct_upstream_dest_test,
    generic_correct_upstream_request_test,
    generic_upstream_headers_verify_test,
    overriden_file_content,
)
from util import GuardedSubprocess

log = logging.getLogger(__name__)


class TestLogsEndpoint:
    def test_if_upstream_headers_are_correct(self,
                                             master_ar_process_perclass,
                                             valid_user_header):

        accel_buff_header = {"X-Accel-Buffering": "TEST"}

        req_headers = copy.deepcopy(valid_user_header)
        req_headers.update(accel_buff_header)

        generic_upstream_headers_verify_test(master_ar_process_perclass,
                                             req_headers,
                                             '/system/v1/logs/v1/foo/bar',
                                             assert_headers=accel_buff_header,
                                             )


class TestService:
    def test_if_websockets_conn_upgrade_is_supported(
            self, master_ar_process_perclass, mocker, valid_user_header):
        headers = copy.deepcopy(valid_user_header)
        headers['Upgrade'] = 'WebSocket'
        headers['Connection'] = 'upgrade'

        generic_upstream_headers_verify_test(master_ar_process_perclass,
                                             headers,
                                             '/service/scheduler-alwaysthere/foo/bar/',
                                             assert_headers=headers,
                                             )

    def test_if_accept_encoding_header_is_removed_from_upstream_request(
            self, master_ar_process_perclass, mocker, valid_user_header):
        headers = copy.deepcopy(valid_user_header)
        headers['Accept-Encoding'] = 'gzip'

        generic_upstream_headers_verify_test(master_ar_process_perclass,
                                             headers,
                                             '/service/scheduler-alwaysthere/foo/bar/',
                                             assert_headers_absent=["Accept-Encoding"],
                                             )


class TestHistoryServiceRouting:
    def test_if_invalid_cache_case_is_handled(
            self, nginx_class, valid_user_header, dns_server_mock):
        ar = nginx_class()
        url = ar.make_url_from_path('/dcos-history-service/foo/bar')

        with GuardedSubprocess(ar):
            # Unfortunatelly there are upstreams that use `leader.mesos` and
            # removing this entry too early will result in Nginx failing to start.
            # So we need to do it right after nginx starts, but before first
            # cache update.
            time.sleep(1)
            dns_server_mock.remove_dns_entry('leader.mesos.')

            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)

        assert resp.status_code == 503
        assert 'cache is invalid' in resp.text

    def test_if_leader_is_unknown_state_is_handled(
            self, nginx_class, valid_user_header):
        ar = nginx_class(host_ip=None)
        url = ar.make_url_from_path('/dcos-history-service/foo/bar')

        with GuardedSubprocess(ar):
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)

        assert resp.status_code == 503
        assert 'Mesos leader is unknown' in resp.text

    def test_if_leader_is_local_state_is_handled(
            self, nginx_class, valid_user_header):
        ar = nginx_class()
        path_sent = '/dcos-history-service/foo/bar?a1=GET+param&a2=foobarism'
        path_expected = '/foo/bar?a1=GET+param&a2=foobarism'

        with GuardedSubprocess(ar):
            generic_correct_upstream_dest_test(
                ar,
                valid_user_header,
                path_sent,
                "http://127.0.0.1:15055")
            generic_correct_upstream_request_test(
                ar,
                valid_user_header,
                path_sent,
                path_expected)
            generic_upstream_headers_verify_test(
                ar,
                valid_user_header,
                path_sent)

    def test_if_leader_is_nonlocal_state_is_handled(
            self, nginx_class, valid_user_header, dns_server_mock):
        ar = nginx_class()
        path_sent = '/dcos-history-service/foo/bar?a1=GET+param&a2=foobarism'
        path_expected = '/dcos-history-service/foo/bar?a1=GET+param&a2=foobarism'
        dns_server_mock.set_dns_entry('leader.mesos.', ip='127.0.0.3')

        with GuardedSubprocess(ar):
            generic_correct_upstream_dest_test(
                ar,
                valid_user_header,
                path_sent,
                "http://127.0.0.3:80")
            generic_correct_upstream_request_test(
                ar,
                valid_user_header,
                path_sent,
                path_expected)
            generic_upstream_headers_verify_test(
                ar,
                valid_user_header,
                path_sent,
                assert_headers={"DCOS-Forwarded": "true"})

    def test_if_proxy_loop_is_handled(
            self, nginx_class, valid_user_header, dns_server_mock):
        ar = nginx_class()
        url = ar.make_url_from_path('/dcos-history-service/foo/bar')

        dns_server_mock.set_dns_entry('leader.mesos.', ip='127.0.0.3')

        h = valid_user_header
        h.update({"DCOS-Forwarded": "true"})

        with GuardedSubprocess(ar):
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=h)

        assert resp.status_code == 503
        assert 'Mesos leader is unknown' in resp.text


class TestMetadata:
    @pytest.mark.parametrize("public_ip", ['1.2.3.4', "10.20.20.30"])
    def test_if_public_ip_detection_works(
            self, valid_user_header, nginx_class, public_ip):
        ar = nginx_class(host_ip=public_ip)
        url = ar.make_url_from_path('/metadata')

        with GuardedSubprocess(ar):
            resp = requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header)

            assert resp.status_code == 200
            resp_data = resp.json()
            assert resp_data['PUBLIC_IPV4'] == public_ip

    def test_if_clusterid_is_returned(
            self, master_ar_process_perclass, valid_user_header):
        url = master_ar_process_perclass.make_url_from_path('/metadata')

        resp = requests.get(
            url,
            allow_redirects=False,
            headers=valid_user_header)

        assert resp.status_code == 200
        resp_data = resp.json()
        assert resp_data['CLUSTER_ID'] == 'fdb1d7c0-06cf-4d65-bb9b-a8920bb854ef'

        with overriden_file_content(
                '/var/lib/dcos/cluster-id',
                "fd21689b-4fe2-4779-8c30-9125149eef11"):
            resp = requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header)

        assert resp.status_code == 200
        resp_data = resp.json()
        assert resp_data['CLUSTER_ID'] == "fd21689b-4fe2-4779-8c30-9125149eef11"

    def test_if_missing_clusterid_file_is_handled(
            self, master_ar_process_perclass, valid_user_header):
        url = master_ar_process_perclass.make_url_from_path('/metadata')

        with overriden_file_content('/var/lib/dcos/cluster-id'):
            os.unlink('/var/lib/dcos/cluster-id')
            resp = requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header)

        assert resp.status_code == 200
        resp_data = resp.json()
        assert 'CLUSTER_ID' not in resp_data
