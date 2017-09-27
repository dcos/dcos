# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import copy
import logging
import os
from contextlib import contextmanager
from http import cookies

import requests

from mocker.endpoints.mesos import AGENT1_ID
from util import LineBufferFilter

log = logging.getLogger(__name__)


def ping_mesos_agent(ar,
                     auth_header,
                     endpoint_id='http://127.0.0.2:15001',
                     expect_status=200,
                     agent_id=AGENT1_ID,
                     timeout=60,
                     ):
    """Test if agent is reachable or not

    Helper function meant to simplify checking mesos agent reachability/mesos
    agent related testing.

    Arguments:
        ar: Admin Router object, an instance of runner.(ee|open).Nginx
        auth_header (dict): headers dict that contains DC/OS authentication
            token. The auth data it contains is invalid.
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


def generic_no_slash_redirect_test(ar, path, code=301):
    """Test if request for location without trailing slash is redirected

    Helper function meant to simplify writing multiple tests testing the
    same thing for different endpoints.

    Arguments:
        ar: Admin Router object, an instance of runner.(ee|open).Nginx
        path (str): path for which request should be made
        code (int): expected http redirect code
    """
    url = ar.make_url_from_path(path)
    r = requests.get(url, allow_redirects=False)

    assert r.status_code == code
    assert r.headers['Location'] == url + '/'


def generic_response_headers_verify_test(
        ar, auth_header, path, assert_headers=None, assert_headers_absent=None):
    """Test if response sent by AR is correct

    Helper function meant to simplify writing multiple tests testing the
    same thing for different endpoints.

    Arguments:
        ar: Admin Router object, an instance of runner.(ee|open).Nginx
        auth_header (dict): headers dict that contains DC/OS authentication
            token. The auth data it contains is valid and the request should be
            accepted.
        path (str): path for which request should be made
        assert_headers (dict): additional headers to test where key is the
            asserted header name and value is expected value
        assert_headers_absent (dict): headers that *MUST NOT* be present in the
            upstream request
    """
    url = ar.make_url_from_path(path)
    resp = requests.get(url,
                        allow_redirects=False,
                        headers=auth_header)

    assert resp.status_code == 200

    if assert_headers is not None:
        for name, value in assert_headers.items():
            verify_header(resp.headers.items(), name, value)
    if assert_headers_absent is not None:
        for name in assert_headers_absent:
            header_is_absent(resp.headers.items(), name)


def generic_upstream_cookies_verify_test(
        ar,
        headers,
        path,
        cookies_to_send=None,
        assert_cookies_present=None,
        assert_cookies_absent=None):
    """Test if cookies that are passed to the upstream by AR are correct

    Helper function meant to simplify writing multiple tests testing the
    same thing for different endpoints.

    Arguments:
        ar: Admin Router object, an instance of runner.(ee|open).Nginx
        headers (dict): headers dict that contains DC/OS authentication token
            and cookies. The auth data it contains must be valid.
        path (str): path for which request should be made
        cookies_to_send (dict): dictionary containing all the cookies that should
            be send in the request
        assert_cookies_present (dict): cookies to test where key is the
            asserted cookie name and value is expected value of the cookie
        assert_cookies_absent (list or set): cookies that *MUST NOT* be present
            in the upstream request
    """
    url = ar.make_url_from_path(path)
    resp = requests.get(url,
                        cookies=cookies_to_send,
                        allow_redirects=False,
                        headers=headers)

    assert resp.status_code == 200

    req_data = resp.json()

    # Let's make sure that we got not more than one 'Cookie' header:
    # https://tools.ietf.org/html/rfc6265#section-5.4
    cookie_headers = []
    for header in req_data['headers']:
        if header[0] == 'Cookie':
            cookie_headers.append(header)
    assert len(cookie_headers) <= 1

    if len(cookie_headers) == 1:
        jar = cookies.SimpleCookie()
        # It is a list containing a single tuple (`header name`, `header value`),
        # we need the second element of it - the value of the header:
        jar.load(cookie_headers[0][1])
    else:
        jar = {}

    if assert_cookies_present is not None:
        jar_cookies_dict = {x: jar[x].value for x in jar if x in assert_cookies_present}
        # We only want to check the keys present in cookies_present_dict
        assert jar_cookies_dict == assert_cookies_present

    if assert_cookies_absent is not None:
        jar_cookies_set = set(jar.keys())
        cookies_absent_set = set(assert_cookies_absent)
        assert jar_cookies_set.intersection(cookies_absent_set) == set()


def generic_upstream_headers_verify_test(
        ar, auth_header, path, assert_headers=None, assert_headers_absent=None):
    """Test if headers sent upstream are correct

    Helper function meant to simplify writing multiple tests testing the
    same thing for different endpoints.

    Arguments:
        ar: Admin Router object, an instance of runner.(ee|open).Nginx
        auth_header (dict): headers dict that contains DC/OS authentication
            token. The auth data it contains is valid and the request should be
            accepted.
        path (str): path for which request should be made
        assert_headers (dict): additional headers to test where key is the
            asserted header name and value is expected value
        assert_headers_absent (dict): headers that *MUST NOT* be present in the
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
        auth_header (dict): headers dict that contains DC/OS authentication
            token. The auth data it contains is valid and the request should be
            accepted.
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
        auth_header (dict): headers dict that contains DC/OS authentication
            token. The auth data it contains is valid and the request should be
            accepted.
        given_path (str): path for which request should be made
        expected_path (str): path that is expected to be sent to upstream
        http_ver (str): http version string that the upstream request should be
            made with
    """
    h = copy.deepcopy(auth_header)
    if http_ver == 'HTTP/1.1':
        # In case of HTTP/1.1 connections, we also need to test if Connection
        # header is cleared.
        h['Connection'] = 'close'
    elif http_ver == 'websockets':
        h['Connection'] = 'close'
        h['Upgrade'] = 'Websockets'

    url = ar.make_url_from_path(given_path)
    resp = requests.get(url,
                        allow_redirects=False,
                        headers=h)

    assert resp.status_code == 200
    req_data = resp.json()
    assert req_data['method'] == 'GET'
    assert req_data['path'] == expected_path
    if http_ver == 'HTTP/1.1':
        header_is_absent(req_data['headers'], 'Connection')
        assert req_data['request_version'] == 'HTTP/1.1'
    elif http_ver == 'websockets':
        verify_header(req_data['headers'], 'Connection', 'upgrade')
        verify_header(req_data['headers'], 'Upgrade', 'Websockets')
        assert req_data['request_version'] == 'HTTP/1.1'
    else:
        assert req_data['request_version'] == http_ver


def generic_location_header_during_redirect_is_adjusted_test(
        ar,
        mocker,
        auth_header,
        endpoint_id,
        basepath,
        location_set,
        location_expected,
        ):
    """Test if the `Location` header is rewritten by AR on redirect.

    This generic test issues a request to AR for a given path and verifies that
    redirect has occurred with the `Location` header contents equal to
    `location_expected` argument.

    Arguments:
        mocker (Mocker): instance of the Mocker class, used for controlling
            upstream HTTP endpoint/mock
        ar: Admin Router object, an instance of `runner.(ee|open).Nginx`.
        auth_header (dict): headers dict that contains DC/OS authentication token.
        endpoint_id (str): id of the endpoint where the upstream request should
            have been sent.
        basepath (str): the URI used by the test harness to issue the request
            to AR, and to which we are expecting AR to respond with rewritten
            `Location` header redirect.
        location_set (str): upstream will send the response with the `Location`
            header set to this value.
        location_expected (str): the expected value of the `Location` header
            after being rewritten/adjusted by AR.
    """
    mocker.send_command(endpoint_id=endpoint_id,
                        func_name='always_redirect',
                        aux_data=location_set)

    url = ar.make_url_from_path(basepath)
    r = requests.get(url, allow_redirects=False, headers=auth_header)

    assert r.status_code == 307
    assert r.headers['Location'] == location_expected


def header_is_absent(headers, header_name):
    """Test if given header is present in the request headers list

    Arguments:
        headers (list): list of tuples containing all the headers present in
            the reflected request data
        header_name (string): name of the header that should not be present/must
            not be set.

    Raises:
        AssertionError: header with the name "header_name" was found in
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


@contextmanager
def overridden_file_content(file_path, new_content=None):
    """Context manager meant to simplify static files testsing

    While inside the context, file can be modified and/or modified content
    may be injected by the context manager itself. Right after context is
    exited, the original file contents are restored.

    Arguments:
        file_path: path the the file that should be "guarded"
        new_content: new content for the file. If None - file contents are not
            changed, "string" objects are translated to binary blob first,
            assuming utf-8 encoding.
    """

    if new_content is not None and not isinstance(new_content, bytes):
        new_content = new_content.encode('utf-8')

    with open(file_path, 'rb+') as fh:
        old_content = fh.read()
        if new_content is not None:
            fh.seek(0)
            fh.write(new_content)
            fh.truncate()

    yield

    with open(file_path, 'wb') as fh:
        fh.write(old_content)


def repo_is_ee():
    """Determine the flavour of the repository

    Return:
        True if repository is EE
    """
    cur_dir = os.path.dirname(__file__)
    ee_tests_dir = os.path.abspath(os.path.join(cur_dir, "..", "..", "tests", "ee"))
    open_tests_dir = os.path.abspath(os.path.join(cur_dir, "..", "..", "tests", "open"))

    is_ee = os.path.isdir(ee_tests_dir) and not os.path.isdir(open_tests_dir)
    is_open = os.path.isdir(open_tests_dir) and not os.path.isdir(ee_tests_dir)

    assert is_ee or is_open, "Unable to determine the variant of the repo"

    return is_ee
