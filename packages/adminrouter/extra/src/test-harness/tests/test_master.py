# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import copy
import logging
import os
import time
import urllib

import pytest
import requests

from generic_test_code.common import (
    generic_correct_upstream_dest_test,
    generic_correct_upstream_request_test,
    generic_upstream_headers_verify_test,
    generic_verify_response_test,
    overridden_file_content,
    verify_header,
)
from util import GuardedSubprocess, LineBufferFilter, SearchCriteria

log = logging.getLogger(__name__)


class TestServiceEndpoint:
    # Majority of /service endpoint tests are done with generic tests framework
    def test_if_accept_encoding_header_is_in_upstream_request(
            self, master_ar_process_perclass, mocker, valid_user_header):
        headers = copy.deepcopy(valid_user_header)
        headers['Accept-Encoding'] = 'gzip'

        generic_upstream_headers_verify_test(master_ar_process_perclass,
                                             headers,
                                             '/service/scheduler-alwaysthere/foo/bar/',
                                             assert_headers={'Accept-Encoding': 'gzip'},
                                             )

    def test_escapes_are_in_upstream_request(
        self, master_ar_process_perclass, mocker, valid_user_header
    ):
        """
        Any space, question mark, or hash escaped in a path element of the
        `/service` endpoint gets passed through to the service unchanged.
        """
        path = urllib.parse.quote('/foo/a ?#z/')
        url = master_ar_process_perclass.make_url_from_path(
            '/service/scheduler-alwaysthere/{}'.format(path)
        )
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 200
        req_data = resp.json()
        assert req_data['method'] == 'GET'
        assert req_data['path'] == path


class TestAgentEndpoint:
    # Tests for /agent endpoint routing are done in test_cache.py
    def test_if_accept_encoding_header_is_removed_from_upstream_request(
            self, master_ar_process_perclass, mocker, valid_user_header):
        headers = copy.deepcopy(valid_user_header)
        headers['Accept-Encoding'] = 'gzip'

        generic_upstream_headers_verify_test(master_ar_process_perclass,
                                             headers,
                                             '/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1/',
                                             assert_headers_absent=["Accept-Encoding"],
                                             )


class TestSystemAgentEndpoint:
    # Tests for /agent endpoint routing are done in test_cache.py
    def test_if_accept_encoding_header_is_removed_from_upstream_request(
            self, master_ar_process_perclass, mocker, valid_user_header):
        headers = copy.deepcopy(valid_user_header)
        headers['Accept-Encoding'] = 'gzip'

        generic_upstream_headers_verify_test(
            master_ar_process_perclass,
            headers,
            '/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S0/logs',
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
        assert 'mesos leader is unknown' in resp.text

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
        assert 'mesos leader is unknown' in resp.text


class TestMetadata:
    @pytest.mark.parametrize("public_ip", ['1.2.3.4', "10.20.20.30"])
    def test_if_public_ip_detection_works(
            self, master_ar_process_perclass, valid_user_header, public_ip):
        url = master_ar_process_perclass.make_url_from_path('/metadata')

        with overridden_file_content(
                '/usr/local/detect_ip_public_data.txt',
                "return ip {}".format(public_ip)):
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

        with overridden_file_content(
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

        with overridden_file_content('/var/lib/dcos/cluster-id'):
            os.unlink('/var/lib/dcos/cluster-id')
            resp = requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header)

        assert resp.status_code == 200
        resp_data = resp.json()
        assert 'CLUSTER_ID' not in resp_data

    def test_if_public_ip_detect_script_failue_is_handled(
            self, master_ar_process_perclass, valid_user_header):
        url = master_ar_process_perclass.make_url_from_path('/metadata')
        filter_regexp = {
            'Traceback \(most recent call last\):': SearchCriteria(1, True),
            ("FileNotFoundError: \[Errno 2\] No such file or directory:"
             " '/usr/local/detect_ip_public_data.txt'"): SearchCriteria(1, True),
        }
        lbf = LineBufferFilter(filter_regexp,
                               line_buffer=master_ar_process_perclass.stderr_line_buffer)

        with lbf, overridden_file_content('/usr/local/detect_ip_public_data.txt'):
            os.unlink('/usr/local/detect_ip_public_data.txt')
            resp = requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header)

        assert resp.status_code == 200
        assert lbf.extra_matches == {}
        resp_data = resp.json()
        assert resp_data['PUBLIC_IPV4'] == "127.0.0.1"

    @pytest.mark.xfail(reason="Needs some refactoring, tracked in DCOS_OSS-1007")
    def test_if_public_ip_detect_script_execution_is_timed_out(
            self, master_ar_process_perclass, valid_user_header):
        url = master_ar_process_perclass.make_url_from_path('/metadata')

        ts_start = time.time()
        with overridden_file_content('/usr/local/detect_ip_public_data.txt',
                                     "timeout 10"):
            requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header)
        ts_total = time.time() - ts_start

        assert ts_total < 10
        # TODO (prozlach): tune it a bit
        # assert resp.status_code == 200
        # resp_data = resp.json()
        # assert resp_data['PUBLIC_IPV4'] == "127.0.0.1"

    @pytest.mark.xfail(reason="Needs some refactoring, tracked in DCOS_OSS-1007")
    def test_if_public_ip_detect_script_nonzero_exit_status_is_handled(
            self, master_ar_process_perclass, valid_user_header):
        url = master_ar_process_perclass.make_url_from_path('/metadata')

        with overridden_file_content(
                '/usr/local/detect_ip_public_data.txt',
                "break with 1"):
            resp = requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header)

        assert resp.status_code == 200
        resp_data = resp.json()
        assert resp_data['PUBLIC_IPV4'] == "127.0.0.1"


class TestUiRoot:
    @pytest.mark.parametrize("uniq_content", ["(｡◕‿‿◕｡)", "plain text 1234"])
    @pytest.mark.parametrize("path", ["plain-ui-testfile.html",
                                      "nest1/nested-ui-testfile.html"])
    def test_if_ui_files_are_handled(
            self,
            master_ar_process_perclass,
            valid_user_header,
            uniq_content,
            path):

        url = master_ar_process_perclass.make_url_from_path('/{}'.format(path))

        with overridden_file_content(
                '/var/lib/dcos/dcos-ui-update-service/dist/ui/{}'.format(path),
                uniq_content):
            resp = requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header)

        assert resp.status_code == 200
        resp.encoding = 'utf-8'
        assert resp.text == uniq_content
        verify_header(resp.headers.items(), 'X-Frame-Options', 'DENY')


class TestMisc:
    @pytest.mark.parametrize("content", ["{'data': '1234'}", "{'data': 'abcd'}"])
    def test_if_buildinfo_is_served(
            self, master_ar_process_perclass, valid_user_header, content):
        url = master_ar_process_perclass.make_url_from_path(
            '/pkgpanda/active.buildinfo.full.json')

        with overridden_file_content(
                '/opt/mesosphere/active.buildinfo.full.json',
                content):
            resp = requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header
                )

        assert resp.status_code == 200
        assert resp.text == content

    @pytest.mark.parametrize("content", ["{'data': '1234'}", "{'data': 'abcd'}"])
    def test_if_dcos_metadata_is_served(
            self, master_ar_process_perclass, valid_user_header, content):
        url = master_ar_process_perclass.make_url_from_path(
            '/dcos-metadata/dcos-version.json')

        with overridden_file_content(
                '/opt/mesosphere/active/dcos-metadata/etc/dcos-version.json',
                content):
            resp = requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header
                )

        assert resp.status_code == 200
        assert resp.text == content

    def test_if_xaccel_header_is_passed_to_client_by_ar(
            self,
            master_ar_process_perclass,
            valid_user_header,
            mocker):

        accel_buff_header = {"X-Accel-Buffering": "TEST"}

        mocker.send_command(
            endpoint_id='http:///run/dcos/dcos-log.sock',
            func_name='set_response_headers',
            aux_data=accel_buff_header,
        )

        generic_verify_response_test(
            master_ar_process_perclass,
            valid_user_header,
            '/system/v1/logs/foo/bar',
            assert_headers=accel_buff_header)
