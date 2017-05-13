# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import collections
import copy
import logging
import time

import pytest
import requests

from generic_test_code.common import (
    generic_correct_upstream_dest_test,
    generic_correct_upstream_request_test,
    generic_no_slash_redirect_test,
    generic_upstream_headers_verify_test,
)
from mocker.endpoints.mesos import AGENT1_ID, AGENT2_ID
from util import GuardedSubprocess

log = logging.getLogger(__name__)

EndpointPathExpectation = collections.namedtuple(
    "EndpointPathExpectation",
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
        [EndpointPathExpectation(
            '/acs/api/v1/foo/bar', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/capabilities', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/cosmos/service/foo/bar', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/dcos-history-service/foo/bar', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/exhibitor/foo/bar', '/foo/bar'),
         EndpointPathExpectation(
            '/exhibitor/', '/'),
         ],
        None, 'HTTP/1.0', True, 'http://127.0.0.1:8181'),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/marathon/v2/apps', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/mesos/master/state-summary', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/mesos_dns/v1/services/_scheduler-alwaysthere._tcp.marathon.mesos', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/metadata', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/navstar/lashup/key', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/package/foo/bar', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/pkgpanda/foo/bar', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/pkgpanda/active.buildinfo.full.json', None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/service/scheduler-alwaysthere/foo/bar', '/foo/bar'),
         EndpointPathExpectation(
            '/service/scheduler-alwaysthere/', '/'),
         ],
        True, 'HTTP/1.1', True, "http://127.0.0.1:16000"),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/agent/{}'.format(AGENT1_ID), "/"),
         EndpointPathExpectation(
            '/agent/{}/'.format(AGENT1_ID), "/"),
         EndpointPathExpectation(
            '/agent/{}/foo/bar'.format(AGENT1_ID), "/foo/bar"),
         ],
        True, "HTTP/1.1", True, "http://127.0.0.2:15001"),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/system/health/v1/foo/bar', '/system/health/v1/foo/bar'),
         EndpointPathExpectation(
            '/system/health/v1/', '/system/health/v1/'),
         EndpointPathExpectation(
            '/system/health/v1', '/system/health/v1'),
         ],
        None, 'HTTP/1.0', True, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/system/v1/agent/{}/logs/v1/foo/bar'.format(AGENT1_ID), None),
         ],
        None, None, None, None),
    EndpointTestConfig(
        [EndpointPathExpectation(
            ('/system/v1/agent/{}'.format(AGENT1_ID) +
             '/logs/v1/foo/bar?key=value&var=num'),
            '/system/v1/logs/v1/foo/bar?key=value&var=num'),
         EndpointPathExpectation(
            ('/system/v1/agent/{}'.format(AGENT1_ID) +
             '/metrics/v0/foo/bar?key=value&var=num'),
            '/system/v1/metrics/v0/foo/bar?key=value&var=num'),
         EndpointPathExpectation(
            ('/system/v1/agent/{}'.format(AGENT1_ID) +
             '/logs/v1/'),
            '/system/v1/logs/v1/'),
         EndpointPathExpectation(
            ('/system/v1/agent/{}'.format(AGENT1_ID) +
             '/metrics/v0/'), '/system/v1/metrics/v0/'),
         EndpointPathExpectation(
            ('/system/v1/agent/{}'.format(AGENT1_ID) +
             '/logs/v1'), '/system/v1/logs/v1'),
         EndpointPathExpectation(
            ('/system/v1/agent/{}'.format(AGENT1_ID) +
             '/metrics/v0'), '/system/v1/metrics/v0'),
         ],
        None, "HTTP/1.1", True, 'http://127.0.0.2:61001'),
    EndpointTestConfig(
        [EndpointPathExpectation(
            ('/system/v1/agent/{}'.format(AGENT2_ID) +
             '/logs/v1/foo/bar?key=value&var=num'),
            '/system/v1/logs/v1/foo/bar?key=value&var=num'),
         EndpointPathExpectation(
            ('/system/v1/agent/{}'.format(AGENT2_ID) +
             '/metrics/v0/foo/bar?key=value&var=num'),
            '/system/v1/metrics/v0/foo/bar?key=value&var=num'),
         EndpointPathExpectation(
            ('/system/v1/agent/{}'.format(AGENT2_ID) +
             '/logs/v1/'),
            '/system/v1/logs/v1/'),
         EndpointPathExpectation(
            ('/system/v1/agent/{}'.format(AGENT2_ID) +
             '/metrics/v0/'), '/system/v1/metrics/v0/'),
         EndpointPathExpectation(
            ('/system/v1/agent/{}'.format(AGENT2_ID) +
             '/logs/v1'), '/system/v1/logs/v1'),
         EndpointPathExpectation(
            ('/system/v1/agent/{}'.format(AGENT2_ID) +
             '/metrics/v0'), '/system/v1/metrics/v0'),
         ],
        None, "HTTP/1.1", True, 'http://127.0.0.3:61001'),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/system/v1/leader/mesos/foo/bar?key=value&var=num',
            '/system/v1/foo/bar?key=value&var=num'),
         EndpointPathExpectation(
            '/system/v1/leader/mesos/', '/system/v1/'),
         EndpointPathExpectation(
            '/system/v1/leader/mesos', '/system/v1'),
         EndpointPathExpectation(
            '/system/v1/leader/marathon/foo/bar?key=value&var=num',
            '/system/v1/foo/bar?key=value&var=num'),
         EndpointPathExpectation(
            '/system/v1/leader/marathon/', '/system/v1/'),
         EndpointPathExpectation(
            '/system/v1/leader/marathon', '/system/v1'),
         ],
        None, 'HTTP/1.1', True, 'http://127.0.0.2:80'),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/system/v1/logs/v1/foo/bar', '/foo/bar'),
         EndpointPathExpectation(
            '/system/v1/logs/v1/', '/'),
         ],
        None, 'HTTP/1.1', True, 'http:///run/dcos/dcos-log.sock'),
    EndpointTestConfig(
        [EndpointPathExpectation(
            '/system/v1/metrics/foo/bar', '/foo/bar'),
         EndpointPathExpectation(
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
LocationRewriteExpectation = collections.namedtuple(
    "LocationRewriteExpectation",
    ('location_set, location_expected')
)

location_header_rewrite_test_config = [
    LocationHeaderRewriteTestConfig(
        "http://127.0.0.1:16000",
        "/service/scheduler-alwaysthere/foo/bar",
        [LocationRewriteExpectation(
            "http://127.0.0.1/service/scheduler-alwaysthere/foo/bar",
            "http://127.0.0.1/service/scheduler-alwaysthere/foo/bar"),
         LocationRewriteExpectation(
             "http://127.0.0.1/foo/bar",
             "http://127.0.0.1/service/scheduler-alwaysthere/foo/bar"),
         LocationRewriteExpectation(
            "/foo/bar",
            "http://127.0.0.1/service/scheduler-alwaysthere/foo/bar"),
         ]),
    LocationHeaderRewriteTestConfig(
        "http://127.0.0.1:8181",
        "/exhibitor/v1/ui/index.html",
        [LocationRewriteExpectation(
            "http://127.0.0.1/exhibitor/v1/ui/index.html",
            "http://127.0.0.1/exhibitor/exhibitor/v1/ui/index.html"),
         ]),
]

location_header_test_params = [
    (x.endpoint_id, x.basepath, y.location_set, y.location_expected)
    for x in location_header_rewrite_test_config for y in x.redirect_testscases]

redirected_paths = [
    '/service/scheduler-alwaysthere',
    '/exhibitor',
    '/system/v1/metrics',
    '/system/v1/logs/v1',
]


class TestMaster:
    @pytest.mark.parametrize("path,expected_upstream", correct_upstream_dest_endpoints)
    def test_if_request_is_sent_to_correct_upstream(
            self,
            master_ar_process_perclass,
            valid_user_header,
            path,
            expected_upstream):

        generic_correct_upstream_dest_test(master_ar_process_perclass,
                                           valid_user_header,
                                           path,
                                           expected_upstream,
                                           )

    @pytest.mark.parametrize("path,pass_authheader", upstream_headers_endpoints)
    def test_if_upstream_headers_are_correct(
            self,
            master_ar_process_perclass,
            valid_user_header,
            path,
            pass_authheader,
            ):

        if pass_authheader is True:
            generic_upstream_headers_verify_test(master_ar_process_perclass,
                                                 valid_user_header,
                                                 path,
                                                 assert_headers=valid_user_header,
                                                 )
        elif pass_authheader is False:
            generic_upstream_headers_verify_test(
                master_ar_process_perclass,
                valid_user_header,
                path,
                assert_headers_absent=["Authorization"]
                )

        # None
        else:
            generic_upstream_headers_verify_test(master_ar_process_perclass,
                                                 valid_user_header,
                                                 path,
                                                 )

    @pytest.mark.parametrize("path,upstream_path,http_ver", correct_upstream_req_endpoints)
    def test_if_upstream_request_is_correct(
            self,
            master_ar_process_perclass,
            valid_user_header,
            path,
            upstream_path,
            http_ver):
        generic_correct_upstream_request_test(master_ar_process_perclass,
                                              valid_user_header,
                                              path,
                                              upstream_path,
                                              http_ver,
                                              )

    @pytest.mark.parametrize(
        "endpoint_id,basepath,location_set,location_expected", location_header_test_params)
    def test_if_location_header_during_redirect_is_adjusted(
            self,
            master_ar_process_perclass,
            mocker,
            valid_user_header,
            endpoint_id,
            basepath,
            location_set,
            location_expected,):
        mocker.send_command(endpoint_id=endpoint_id,
                            func_name='always_redirect',
                            aux_data=location_set)

        url = master_ar_process_perclass.make_url_from_path(basepath)
        r = requests.get(url, allow_redirects=False, headers=valid_user_header)

        assert r.status_code == 307
        assert r.headers['Location'] == location_expected

    @pytest.mark.parametrize('path', redirected_paths)
    def test_redirect_req_without_slash(self, master_ar_process_perclass, path):
        generic_no_slash_redirect_test(master_ar_process_perclass, path)


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
