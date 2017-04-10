# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import logging

import requests

from util import LineBufferFilter

log = logging.getLogger(__name__)


def ping_mesos_agent(ar,
                     auth_header,
                     endpoint_id='http://127.0.0.2:15001',
                     expect_status=200,
                     agent_id='de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1',
                     timeout=60,
                     ):
    """Test if agent is reachable or not

    Helper function meant to simplify checking mesos agent reachability/mesos
    agent related testing.

    Arguments:
        ar: Admin Router object, an instance of runner.(ee|open).Nginx
        auth_header (dict): headers dict that contains JWT. The auth data it
            contains is invalid.
        expect_status (int): HTTP status to expect
        endpoint_id (str): if expect_status==200 - id of the endpoint that
            should respoind to the request
        agent_id (str): id of the agent to ping
    """
    url = ar.make_url_from_path('/agent/{}/blah/blah'.format(agent_id))

    resp = requests.get(url,
                        allow_redirects=False,
                        headers=auth_header,
                        timeout=timeout)

    assert resp.status_code == expect_status
    if expect_status == 200:
        req_data = resp.json()
        assert req_data['endpoint_id'] == endpoint_id


def generic_no_slash_redirect_test(ar, path):
    """Test if request for location without trailing slash is redirected

    Helper function meant to simplify writing multiple tests testing the
    same thing for different endpoints.

    Arguments:
        ar: Admin Router object, an instance of runner.(ee|open).Nginx
        path (str): path for which request should be made
    """
    url = ar.make_url_from_path(path)
    r = requests.get(url, allow_redirects=False)

    assert r.status_code == 301


def generic_upstream_headers_verify_test(
        ar, auth_header, path, assert_headers=None, assert_headers_absent=None):
    """Test if headers sent upstream are correct

    Helper function meant to simplify writing multiple tests testing the
    same thing for different endpoints.

    Arguments:
        ar: Admin Router object, an instance of runner.(ee|open).Nginx
        auth_header (dict): headers dict that contains JWT. The auth data it
            contains is valid and the request should be accepted.
        path (str): path for which request should be made
        assert_headers (dict): additional headers to test where key is the
            asserted header name and value is expected value
        assert_header_absent (dict): headers that *MUST NOT* be present in the
            upstream request
    """
    url = ar.make_url_from_path(path)
    resp = requests.get(url,
                        allow_redirects=False,
                        headers=auth_header)

    assert resp.status_code == 200

    req_data = resp.json()

    verify_header(req_data['headers'], 'X-Forwarded-For', '127.0.0.1')
    verify_header(req_data['headers'], 'X-Forwarded-Proto', 'http')
    verify_header(req_data['headers'], 'X-Real-IP', '127.0.0.1')

    if assert_headers is not None:
        for name, value in assert_headers.items():
            verify_header(req_data['headers'], name, value)
    if assert_headers_absent is not None:
        for name in assert_headers_absent:
            header_is_absent(req_data['headers'], name)


def generic_correct_upstream_dest_test(ar, auth_header, path, endpoint_id):
    """Test if upstream request has been sent to correct upstream

    Helper function meant to simplify writing multiple tests testing the
    same thing for different endpoints.

    Arguments:
        ar: Admin Router object, an instance of runner.(ee|open).Nginx
        auth_header (dict): headers dict that contains JWT. The auth data it
            contains is valid and the request should be accepted.
        path (str): path for which request should be made
        endpoint_id (str): id of the endpoint where the upstream request should
            have been sent
    """
    url = ar.make_url_from_path(path)
    resp = requests.get(url,
                        allow_redirects=False,
                        headers=auth_header)

    assert resp.status_code == 200
    req_data = resp.json()
    assert req_data['endpoint_id'] == endpoint_id


def generic_correct_upstream_request_test(
        ar, auth_header, given_path, expected_path, http_ver='HTTP/1.0'):
    """Test if path component of the request sent upstream is correct.

    Helper function meant to simplify writing multiple tests testing the
    same thing for different endpoints.

    Arguments:
        ar: Admin Router object, an instance of runner.(ee|open).Nginx
        auth_header (dict): headers dict that contains JWT. The auth data it
            contains is valid and the request should be accepted.
        given_path (str): path for which request should be made
        expected_path (str): path that is expected to be sent to upstream
        http_ver (str): http version string that the upstream request should be
            made with
    """
    url = ar.make_url_from_path(given_path)
    resp = requests.get(url,
                        allow_redirects=False,
                        headers=auth_header)

    assert resp.status_code == 200
    req_data = resp.json()
    assert req_data['method'] == 'GET'
    assert req_data['path'] == expected_path
    assert req_data['request_version'] == http_ver


def header_is_absent(headers, header_name):
    """Test if given header is present in the request headers list

    Arguments:
        headers (list): list of tuples containing all the headers present in
            the reflected request data
        header_name (string): name of the header that should not be present/must
            not be set.

    Raises:
        AssertionErrror: header with the name "header_name" was found in
        supplied header list.
    """
    for header in headers:
        assert header[0] != header_name


def verify_header(headers, header_name, header_value):
    """Asserts that particular header exists and has correct value.

    Helper function for checking if header with given name has been defined
    with correct value in given headers list. The headers list is in format
    defined by requests module.

    Presence of more than one header with given name or incorrect value raises
    assert statement.

    Args:
        header_name (str): header name to seek
        header_value (str): expected value of the header
        headers (obj: [('h1', 'v1'), ('h2', 'v2'), ...]): a list of header
            name-val tuples

    Raises:
        AssertionError: header has not been found, there is more than one header
            with given name or header has incorrect value
    """
    matching_headers = list()

    for header in headers:
        if header[0] == header_name:
            matching_headers.append(header)

    # Hmmm....
    if len(matching_headers) != 1:
        if len(matching_headers) == 0:
            msg = "Header `{}` has not been found".format(header_name)
        elif len(matching_headers) > 1:
            msg = "More than one `{}` header has been found".format(header_name)

        assert len(matching_headers) == 1, msg

    assert matching_headers[0][1] == header_value


def assert_endpoint_response(
        ar,
        path,
        code,
        assert_stderr=None,
        headers=None,
        cookies=None,
        assertions=None
        ):
    """Asserts response code and log messages in Admin Router stderr for
    request against specified path.

    Arguments:
        ar (Nginx): Running instance of the AR
        code (int): Expected response code
        assert_stderr (dict): LineBufferFilter compatible definition of messages
            to assert
        cookies (dict): Optionally provide request cookies
        headers (dict): Optionally provide request headers
        assertions (List[lambda r]) Optionally provide additional assertions
            for the response
    """
    def body():
        r = requests.get(
            ar.make_url_from_path(path),
            headers=headers,
            cookies=cookies,
            )
        assert r.status_code == code
        if assertions:
            for func in assertions:
                assert func(r)

    if assert_stderr is not None:
        lbf = LineBufferFilter(assert_stderr, line_buffer=ar.stderr_line_buffer)
        with lbf:
            body()
        assert lbf.extra_matches == {}
    else:
        body()
