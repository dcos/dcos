# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import pytest
import requests

from generic_test_code import (
    generic_correct_upstream_dest_test,
    generic_correct_upstream_request_test,
    generic_upstream_headers_verify_test,
    generic_no_slash_redirect_test,
)


class TestExhibitorEndpoint():
    def test_redirect_req_without_slash(self, master_ar_process):
        generic_no_slash_redirect_test(master_ar_process, '/exhibitor')

    def test_if_exhibitor_endpoint_handles_redirects_properly(
            self, master_ar_process, mocker, superuser_user_header):
        location_sent = 'http://127.0.0.1/exhibitor/v1/ui/index.html'
        location_expected = 'http://127.0.0.1/exhibitor/exhibitor/v1/ui/index.html'
        mocker.send_command(endpoint_id='http://127.0.0.1:8181',
                            func_name='always_redirect',
                            aux_data=location_sent)

        url = master_ar_process.make_url_from_path("/exhibitor/v1/ui/index.html")
        r = requests.get(url, allow_redirects=False, headers=superuser_user_header)

        assert r.status_code == 307
        assert r.headers['Location'] == location_expected

    def test_if_request_is_sent_to_correct_upstream(self,
                                                    master_ar_process,
                                                    superuser_user_header):

        generic_correct_upstream_dest_test(master_ar_process,
                                           superuser_user_header,
                                           '/exhibitor/some/path',
                                           'http://127.0.0.1:8181',
                                           )

    def test_if_upstream_request_is_correct(self,
                                            master_ar_process,
                                            superuser_user_header):

        generic_correct_upstream_request_test(master_ar_process,
                                              superuser_user_header,
                                              '/exhibitor/some/path',
                                              '/some/path',
                                              )

    def test_if_upstream_headers_are_correct(self,
                                             master_ar_process,
                                             superuser_user_header):

        generic_upstream_headers_verify_test(master_ar_process,
                                             superuser_user_header,
                                             '/exhibitor/some/path',
                                             )


agent_prefix = '/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1'


class TestAgentEndpoint():
    # FIXME: Figure out how we can test disable-request-response-buffering.conf

    def test_if_request_is_sent_to_correct_upstream(self,
                                                    master_ar_process,
                                                    superuser_user_header):

        generic_correct_upstream_dest_test(master_ar_process,
                                           superuser_user_header,
                                           agent_prefix + "/foo/bar",
                                           'http://127.0.0.2:15001',
                                           )

    @pytest.mark.parametrize("path_given,path_expected",
                             [("/foo/bar", "/foo/bar"),
                              ("", "/"),
                              ("/", "/"),
                              ])
    def test_if_upstream_request_is_correct(self,
                                            master_ar_process,
                                            superuser_user_header,
                                            path_given,
                                            path_expected):

        prefixed_pg = agent_prefix + path_given
        generic_correct_upstream_request_test(master_ar_process,
                                              superuser_user_header,
                                              prefixed_pg,
                                              path_expected,
                                              http_ver="HTTP/1.1",
                                              )

    def test_if_upstream_headers_are_correct(self,
                                             master_ar_process,
                                             superuser_user_header):

        path = '/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1/logs/v1/foo/bar'
        generic_upstream_headers_verify_test(master_ar_process,
                                             superuser_user_header,
                                             path,
                                             )


class TestMetricsEndpoint():
    def test_redirect_req_without_slash(self, master_ar_process):
        generic_no_slash_redirect_test(master_ar_process, '/system/v1/metrics')

    def test_if_request_is_sent_to_correct_upstream(self,
                                                    master_ar_process,
                                                    superuser_user_header):

        generic_correct_upstream_dest_test(master_ar_process,
                                           superuser_user_header,
                                           '/system/v1/metrics/foo/bar',
                                           'http:///run/dcos/dcos-metrics-master.sock',
                                           )

    @pytest.mark.parametrize("path_given,path_expected",
                             [("/system/v1/metrics/foo/bar", "/foo/bar"),
                              ("/system/v1/metrics/", "/"),
                              ])
    def test_if_upstream_request_is_correct(self,
                                            master_ar_process,
                                            superuser_user_header,
                                            path_given,
                                            path_expected):

        generic_correct_upstream_request_test(master_ar_process,
                                              superuser_user_header,
                                              path_given,
                                              path_expected,
                                              )

    def test_if_upstream_headers_are_correct(self,
                                             master_ar_process,
                                             superuser_user_header):

        generic_upstream_headers_verify_test(master_ar_process,
                                             superuser_user_header,
                                             '/system/v1/metrics/foo/bar',
                                             )


class TestLogsEndpoint():
    def test_redirect_req_without_slash(self, master_ar_process):
        generic_no_slash_redirect_test(master_ar_process, '/system/v1/logs/v1')

    def test_if_request_is_sent_to_correct_upstream(self,
                                                    master_ar_process,
                                                    superuser_user_header):

        generic_correct_upstream_dest_test(master_ar_process,
                                           superuser_user_header,
                                           '/system/v1/logs/v1/foo/bar',
                                           'http:///run/dcos/dcos-log.sock',
                                           )

    @pytest.mark.parametrize("path_given,path_expected",
                             [("/system/v1/logs/v1/foo/bar", "/foo/bar"),
                              ("/system/v1/logs/v1/", "/"),
                              ])
    def test_if_upstream_request_is_correct(self,
                                            master_ar_process,
                                            superuser_user_header,
                                            path_given,
                                            path_expected):

        generic_correct_upstream_request_test(master_ar_process,
                                              superuser_user_header,
                                              path_given,
                                              path_expected,
                                              http_ver="HTTP/1.1"
                                              )

    def test_if_upstream_headers_are_correct(self,
                                             master_ar_process,
                                             superuser_user_header):

        generic_upstream_headers_verify_test(master_ar_process,
                                             superuser_user_header,
                                             '/system/v1/logs/v1/foo/bar',
                                             )


class TestHealthEndpoint():
    @pytest.mark.parametrize("path_given,path_expected",
                             [("/system/health/v1/foo/bar", "/system/health/v1/foo/bar"),
                              ("/system/health/v1/", "/system/health/v1/"),
                              ("/system/health/v1", "/system/health/v1"),
                              ])
    def test_if_upstream_request_is_correct(self,
                                            master_ar_process,
                                            superuser_user_header,
                                            path_given,
                                            path_expected):

        generic_correct_upstream_request_test(master_ar_process,
                                              superuser_user_header,
                                              path_given,
                                              path_expected,
                                              )

    def test_if_upstream_headers_are_correct(self,
                                             master_ar_process,
                                             superuser_user_header):

        generic_upstream_headers_verify_test(master_ar_process,
                                             superuser_user_header,
                                             '/system/health/v1/foo/bar',
                                             )


class TestSystemAPIAgentProxing():
    @pytest.mark.parametrize("prefix", [("/logs/v1"),
                                        ("/metrics/v0"),
                                        ("/logs/v1/foo/bar"),
                                        ("/metrics/v0/baz/baf"),
                                        ])
    @pytest.mark.parametrize("agent,endpoint", [
        ("de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1", 'http://127.0.0.2:61001'),
        ("de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S0", 'http://127.0.0.3:61001'),
    ])
    def test_if_request_is_sent_to_correct_upstream(self,
                                                    master_ar_process,
                                                    superuser_user_header,
                                                    agent,
                                                    endpoint,
                                                    prefix):

        # FIXME - these are very simple tests for now, need to think how to test
        # streaming api better. ATM we only test if HTTP is set to 1.1 for streaming
        # stuff.
        uri_path = '/system/v1/agent/{}{}'.format(agent, prefix)
        generic_correct_upstream_dest_test(master_ar_process,
                                           superuser_user_header,
                                           uri_path,
                                           endpoint,
                                           )

    @pytest.mark.parametrize("prefix", [("/logs/v1"),
                                        ("/metrics/v0"),
                                        ])
    @pytest.mark.parametrize("sent,expected", [('/foo/bar?key=value&var=num',
                                                '/foo/bar?key=value&var=num'),
                                               ('/foo/bar/baz',
                                                '/foo/bar/baz'),
                                               ('/',
                                                '/'),
                                               ('',
                                                ''),
                                               ])
    def test_if_http_11_is_enabled(self,
                                   master_ar_process,
                                   superuser_user_header,
                                   sent,
                                   expected,
                                   prefix):
        path_sent_fmt = '/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1{}{}'
        path_expected_fmt = '/system/v1{}{}'
        generic_correct_upstream_request_test(master_ar_process,
                                              superuser_user_header,
                                              path_sent_fmt.format(prefix, sent),
                                              path_expected_fmt.format(prefix, expected),
                                              'HTTP/1.1'
                                              )

    @pytest.mark.parametrize("prefix", [("/logs/v1"),
                                        ("/metrics/v0"),
                                        ])
    def test_if_upstream_headers_are_correct(self,
                                             master_ar_process,
                                             superuser_user_header,
                                             prefix,
                                             ):

        path_fmt = '/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1{}/foo/bar'
        generic_upstream_headers_verify_test(master_ar_process,
                                             superuser_user_header,
                                             path_fmt.format(prefix),
                                             )


class TestSystemApiLeaderProxing():
    def test_if_request_is_sent_to_the_current_mesos_leader(self,
                                                            master_ar_process,
                                                            superuser_user_header):

        # FIXME: using MesosDNS `leader.mesos` alias makes things hard to test.
        # Dropping in in favour of cache+API call would improve reliability as
        # well. So no "changing the leader and testing results tests for now"
        generic_correct_upstream_dest_test(master_ar_process,
                                           superuser_user_header,
                                           '/system/v1/leader/mesos/foo/bar',
                                           'http://127.0.0.2:80',
                                           )

    def test_if_request_is_sent_to_the_current_marathon_leader(
            self, master_ar_process, superuser_user_header):

        generic_correct_upstream_dest_test(master_ar_process,
                                           superuser_user_header,
                                           '/system/v1/leader/marathon/foo/bar',
                                           'http://127.0.0.2:80',
                                           )

        # Changing leader is covered in cache tests

    @pytest.mark.parametrize("endpoint_type", [("marathon"),
                                               ("mesos"),
                                               ])
    @pytest.mark.parametrize("sent,expected", [('/foo/bar?key=value&var=num',
                                                '/foo/bar?key=value&var=num'),
                                               ('/foo/bar/baz',
                                                '/foo/bar/baz'),
                                               ('/',
                                                '/'),
                                               ('',
                                                ''),
                                               ])
    def test_if_http11_is_enabled(self,
                                  master_ar_process,
                                  superuser_user_header,
                                  sent,
                                  expected,
                                  endpoint_type):

        path_sent = '/system/v1/leader/mesos' + sent
        path_expected = '/system/v1' + expected
        generic_correct_upstream_request_test(master_ar_process,
                                              superuser_user_header,
                                              path_sent,
                                              path_expected,
                                              http_ver="HTTP/1.1"
                                              )

    @pytest.mark.parametrize("endpoint_type", [("marathon"),
                                               ("mesos"),
                                               ])
    def test_if_upstream_headers_are_correct(self,
                                             master_ar_process,
                                             superuser_user_header,
                                             endpoint_type,
                                             ):

        path_fmt = '/system/v1/leader/{}/foo/bar/bzzz'
        generic_upstream_headers_verify_test(master_ar_process,
                                             superuser_user_header,
                                             path_fmt.format(endpoint_type),
                                             )
