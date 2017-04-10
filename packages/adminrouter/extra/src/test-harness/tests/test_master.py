# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import collections
import copy
import logging

import pytest
import requests

from generic_test_code.common import (
    generic_correct_upstream_dest_test,
    generic_correct_upstream_request_test,
    generic_no_slash_redirect_test,
    generic_upstream_headers_verify_test,
)

log = logging.getLogger(__name__)

EndpointTestPaths = collections.namedtuple(
    "EndpointTestPaths",
    ("sent_path, expected_path")
)

EndpointTestConfig = collections.namedtuple(
    "EndpointTestConfig",
    ('test_paths,'
     'jwt_forwarded, upstream_http_ver, upstream_headers, correct_upstream'),
)

# TODO: This is WIP/POC
endpoint_test_configuration = [
    EndpointTestConfig(
        [EndpointTestPaths(
            '/acs/api/v1/foo/bar', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/capabilities', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/cosmos/service/foo/bar', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/dcos-history-service/foo/bar', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/exhibitor/foo/bar', '/foo/bar'),
         EndpointTestPaths(
            '/exhibitor/', '/'),
         ],
        None, 'HTTP/1.0', True, 'http://127.0.0.1:8181'),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/marathon/v2/apps', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/mesos/master/state-summary', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/mesos_dns/v1/services/_nginx-alwaysthere._tcp.marathon.mesos', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/metadata', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/navstar/lashup/key', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/package/foo/bar', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/pkgpanda/foo/bar', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/pkgpanda/active.buildinfo.full.json', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/service/nginx-alwaysthere/foo/bar', '/foo/bar'),
         EndpointTestPaths(
            '/service/nginx-alwaysthere/', '/'),
         ],
        True, 'HTTP/1.1', True, "http://127.0.0.1:16000"),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1', "/"),
         EndpointTestPaths(
            '/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1/', "/"),
         EndpointTestPaths(
            '/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1/foo/bar', "/foo/bar"),
         ],
        True, "HTTP/1.1", True, "http://127.0.0.2:15001"),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/system/health/v1/foo/bar', '/system/health/v1/foo/bar'),
         EndpointTestPaths(
            '/system/health/v1/', '/system/health/v1/'),
         EndpointTestPaths(
            '/system/health/v1', '/system/health/v1'),
         ],
        None, 'HTTP/1.0', True, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1/logs/v1/foo/bar', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointTestPaths(
            ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1'
             '/logs/v1/foo/bar?key=value&var=num'),
            '/system/v1/logs/v1/foo/bar?key=value&var=num'),
         EndpointTestPaths(
            ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1'
             '/metrics/v0/foo/bar?key=value&var=num'),
            '/system/v1/metrics/v0/foo/bar?key=value&var=num'),
         EndpointTestPaths(
            ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1'
             '/logs/v1/'),
            '/system/v1/logs/v1/'),
         EndpointTestPaths(
            ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1'
             '/metrics/v0/'), '/system/v1/metrics/v0/'),
         EndpointTestPaths(
            ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1'
             '/logs/v1'), '/system/v1/logs/v1'),
         EndpointTestPaths(
            ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1'
             '/metrics/v0'), '/system/v1/metrics/v0'),
         ],
        None, "HTTP/1.1", True, 'http://127.0.0.2:61001'),
    EndpointTestConfig(
        [EndpointTestPaths(
            ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S0'
             '/logs/v1/foo/bar?key=value&var=num'),
            '/system/v1/logs/v1/foo/bar?key=value&var=num'),
         EndpointTestPaths(
            ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S0'
             '/metrics/v0/foo/bar?key=value&var=num'),
            '/system/v1/metrics/v0/foo/bar?key=value&var=num'),
         EndpointTestPaths(
            ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S0'
             '/logs/v1/'),
            '/system/v1/logs/v1/'),
         EndpointTestPaths(
            ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S0'
             '/metrics/v0/'), '/system/v1/metrics/v0/'),
         EndpointTestPaths(
            ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S0'
             '/logs/v1'), '/system/v1/logs/v1'),
         EndpointTestPaths(
            ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S0'
             '/metrics/v0'), '/system/v1/metrics/v0'),
         ],
        None, "HTTP/1.1", True, 'http://127.0.0.3:61001'),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/system/v1/leader/mesos/foo/bar?key=value&var=num',
            '/system/v1/foo/bar?key=value&var=num'),
         EndpointTestPaths(
            '/system/v1/leader/mesos/', '/system/v1/'),
         EndpointTestPaths(
            '/system/v1/leader/mesos', '/system/v1'),
         EndpointTestPaths(
            '/system/v1/leader/marathon/foo/bar?key=value&var=num',
            '/system/v1/foo/bar?key=value&var=num'),
         EndpointTestPaths(
            '/system/v1/leader/marathon/', '/system/v1/'),
         EndpointTestPaths(
            '/system/v1/leader/marathon', '/system/v1'),
         ],
        None, 'HTTP/1.1', True, 'http://127.0.0.2:80'),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/system/v1/logs/v1/foo/bar', '/foo/bar'),
         EndpointTestPaths(
            '/system/v1/logs/v1/', '/'),
         ],
        None, 'HTTP/1.1', True, 'http:///run/dcos/dcos-log.sock'),
    EndpointTestConfig(
        [EndpointTestPaths(
            '/system/v1/metrics/foo/bar', '/foo/bar'),
         EndpointTestPaths(
            '/system/v1/metrics/', '/'),
         ],
        None, 'HTTP/1.0', True, 'http:///run/dcos/dcos-metrics-master.sock'),
]

correct_upstream_req_endpoints = []
for x in endpoint_test_configuration:
    if x.upstream_http_ver is not None:
        for y in x.test_paths:
            if y.expected_path is not None:
                e = (y.sent_path, y.expected_path, x.upstream_http_ver)
                correct_upstream_req_endpoints.append(e)

upstream_headers_endpoints = []
for x in endpoint_test_configuration:
    if x.upstream_headers is not None:
        for y in x.test_paths:
            e = (y.sent_path, x.jwt_forwarded)
            upstream_headers_endpoints.append(e)

correct_upstream_dest_endpoints = []
for x in endpoint_test_configuration:
    if x.correct_upstream is not None:
        for y in x.test_paths:
            e = (y.sent_path, x.correct_upstream)
            correct_upstream_dest_endpoints.append(e)

LocationHeaderRewriteTestConfig = collections.namedtuple(
    "LocationHeaderRewriteTestConfig",
    ('endpoint_id, '
     'basepath, '
     'redirect_testscases')
)
LocationHeaderRewriteTestCase = collections.namedtuple(
    "LocationHeaderRewriteTestCase",
    ('location_set, location_expected')
)

redirect_test_configuration = [
    LocationHeaderRewriteTestConfig(
        "http://127.0.0.1:16000",
        "/service/nginx-alwaysthere/foo/bar",
        [LocationHeaderRewriteTestCase(
            "http://127.0.0.1/service/nginx-alwaysthere/foo/bar",
            "http://127.0.0.1/service/nginx-alwaysthere/foo/bar"),
         LocationHeaderRewriteTestCase(
             "http://127.0.0.1/foo/bar",
             "http://127.0.0.1/service/nginx-alwaysthere/foo/bar"),
         LocationHeaderRewriteTestCase(
            "/foo/bar",
            "http://127.0.0.1/service/nginx-alwaysthere/foo/bar"),
         ]),
    LocationHeaderRewriteTestConfig(
        "http://127.0.0.1:8181",
        "/exhibitor/v1/ui/index.html",
        [LocationHeaderRewriteTestCase(
            "http://127.0.0.1/exhibitor/v1/ui/index.html",
            "http://127.0.0.1/exhibitor/exhibitor/v1/ui/index.html"),
         ]),
]

location_header_test_params = [
    (x.endpoint_id, x.basepath, y.location_set, y.location_expected)
    for x in redirect_test_configuration for y in x.redirect_testscases]

redirected_paths = [
    '/service/nginx-alwaysthere',
    '/exhibitor',
    '/system/v1/metrics',
    '/system/v1/logs/v1',
]


class TestMaster:
    @pytest.mark.parametrize("path,expected_upstream", correct_upstream_dest_endpoints)
    def test_if_request_is_sent_to_correct_upstream(
            self,
            master_ar_process,
            valid_user_header,
            path,
            expected_upstream):

        generic_correct_upstream_dest_test(master_ar_process,
                                           valid_user_header,
                                           path,
                                           expected_upstream,
                                           )

    @pytest.mark.parametrize("path,pass_authheader", upstream_headers_endpoints)
    def test_if_upstream_headers_are_correct(
            self,
            master_ar_process,
            valid_user_header,
            path,
            pass_authheader,
            ):

        if pass_authheader is True:
            generic_upstream_headers_verify_test(master_ar_process,
                                                 valid_user_header,
                                                 path,
                                                 assert_headers=valid_user_header,
                                                 )
        elif pass_authheader is False:
            generic_upstream_headers_verify_test(
                master_ar_process,
                valid_user_header,
                path,
                assert_headers_absent=["Authorization"]
                )

        # None
        else:
            generic_upstream_headers_verify_test(master_ar_process,
                                                 valid_user_header,
                                                 path,
                                                 )

    @pytest.mark.parametrize("path,upstream_path,http_ver", correct_upstream_req_endpoints)
    def test_if_upstream_request_is_correct(
            self,
            master_ar_process,
            valid_user_header,
            path,
            upstream_path,
            http_ver):
        generic_correct_upstream_request_test(master_ar_process,
                                              valid_user_header,
                                              path,
                                              upstream_path,
                                              http_ver,
                                              )

    @pytest.mark.parametrize(
        "endpoint_id,basepath,location_set,location_expected", location_header_test_params)
    def test_if_location_header_during_redirect_is_adjusted(
            self,
            master_ar_process,
            mocker,
            valid_user_header,
            endpoint_id,
            basepath,
            location_set,
            location_expected,):
        mocker.send_command(endpoint_id=endpoint_id,
                            func_name='always_redirect',
                            aux_data=location_set)

        url = master_ar_process.make_url_from_path(basepath)
        r = requests.get(url, allow_redirects=False, headers=valid_user_header)

        assert r.status_code == 307
        assert r.headers['Location'] == location_expected

    @pytest.mark.parametrize('path', redirected_paths)
    def test_redirect_req_without_slash(self, master_ar_process, path):
        generic_no_slash_redirect_test(master_ar_process, path)


class TestLogsEndpoint:
    def test_if_upstream_headers_are_correct(self,
                                             master_ar_process,
                                             valid_user_header):

        accel_buff_header = {"X-Accel-Buffering": "TEST"}

        req_headers = copy.deepcopy(valid_user_header)
        req_headers.update(accel_buff_header)

        generic_upstream_headers_verify_test(master_ar_process,
                                             req_headers,
                                             '/system/v1/logs/v1/foo/bar',
                                             assert_headers=accel_buff_header,
                                             )


class TestService:
    def test_if_websockets_conn_upgrade_is_supported(
            self, master_ar_process, mocker, valid_user_header):
        headers = copy.deepcopy(valid_user_header)
        headers['Upgrade'] = 'WebSocket'
        headers['Connection'] = 'upgrade'

        generic_upstream_headers_verify_test(master_ar_process,
                                             headers,
                                             '/service/nginx-alwaysthere/foo/bar/',
                                             assert_headers=headers,
                                             )

    def test_if_accept_encoding_header_is_removed_from_upstream_request(
            self, master_ar_process, mocker, valid_user_header):
        headers = copy.deepcopy(valid_user_header)
        headers['Accept-Encoding'] = 'gzip'

        generic_upstream_headers_verify_test(master_ar_process,
                                             headers,
                                             '/service/nginx-alwaysthere/foo/bar/',
                                             assert_headers_absent=["Accept-Encoding"],
                                             )
