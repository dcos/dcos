"""Various helpers for test runners and integration testing directly
"""
import atexit
import copy
import functools
import logging
import os
import tempfile
import time
from collections import namedtuple
from functools import wraps

import requests
import retrying
from botocore.exceptions import ClientError, WaiterError

Host = namedtuple('Host', ['private_ip', 'public_ip'])
SshInfo = namedtuple('SshInfo', ['user', 'home_dir'])


def path_join(p1, p2):
    return '{}/{}'.format(p1.rstrip('/'), p2.lstrip('/'))


class DcosUser:
    """A lightweight user representation."""
    def __init__(self, auth_json):
        self.auth_json = auth_json
        self.auth_header = {}
        self.auth_token = None
        self.auth_cookie = None

    def authenticate(self, cluster):
        logging.info('Attempting authentication')
        # explicitly use a session with no user authentication for requesting auth headers
        if cluster.web_auth_default_user:
            post = cluster.get_user_session(None).post
        else:
            post = cluster.post
        r = post('/acs/api/v1/auth/login', json=self.auth_json)
        r.raise_for_status()
        logging.info('Received authorization blob: {}'.format(r.json()))
        assert r.ok, 'Authentication failed with status_code: {}'.format(r.status_code)
        self.auth_token = r.json()['token']
        self.auth_header = {'Authorization': 'token={}'.format(self.auth_token)}
        self.auth_cookie = r.cookies['dcos-acs-auth-cookie']
        logging.info('Authentication successful')


class ApiClient():

    def __init__(self, default_host_url, api_base, default_headers=None, ca_cert_path=None):
        self.default_host_url = default_host_url
        self.api_base = api_base
        if default_headers is None:
            default_headers = dict()
        self.default_headers = default_headers
        self.ca_cert_path = ca_cert_path

    def request_wrapper(self, request_fn, path, host_url=None, **kwargs):
        """
        Makes a request with default headers + user auth headers if necessary
        If self.ca_cert_path is set, this method will pass it to requests
        Args:
            method: (str) name of method for requests.request
            path: see get_url()
            host_url: override the client's default host URL
            **kwargs: any optional arguments to be passed to requests.request
        """
        headers = copy.copy(self.default_headers)

        # allow kwarg to override verification so client can be used generically
        if self.ca_cert_path and 'verify' not in kwargs:
            kwargs['verify'] = self.ca_cert_path

        if self.api_base:
            path = path_join(self.api_base, path)

        request_url = path_join(host_url if host_url else self.default_host_url, path)
        headers.update(kwargs.pop('headers', {}))
        logging.info('Request method {}: {}'.format(request_fn.__name__, request_url))
        logging.debug('Reqeust kwargs: {}'.format(kwargs))
        logging.debug('Request headers: {}'.format(headers))
        return request_fn(request_url, headers=headers, **kwargs)

    def wrapped_request(self, request_fn, *args, **kwargs):
        """Thin wrapper to allow wrapping requests dynamically by mapping
        a function to self.request_wrapper
        """
        return self.request_wrapper(request_fn, *args, **kwargs)

    get = functools.partialmethod(wrapped_request, requests.request.get)
    post = functools.partialmethod(wrapped_request, requests.request.post)
    put = functools.partialmethod(wrapped_request, requests.request.put)
    delete = functools.partialmethod(wrapped_request, requests.request.delete)
    options = functools.partialmethod(wrapped_request, requests.request.options)
    head = functools.partialmethod(wrapped_request, requests.request.head)
    patch = functools.partialmethod(wrapped_request, requests.request.patch)
    delete = functools.partialmethod(wrapped_request, requests.request.delete)


def retry_boto_rate_limits(boto_fn, wait=2, timeout=60 * 60):
    """Decorator to make boto functions resilient to AWS rate limiting and throttling.
    If one of these errors is encounterd, the function will sleep for a geometrically
    increasing amount of time
    """
    @wraps(boto_fn)
    def ignore_rate_errors(*args, **kwargs):
        local_wait = copy.copy(wait)
        local_timeout = copy.copy(timeout)
        while local_timeout > 0:
            next_time = time.time() + local_wait
            try:
                return boto_fn(*args, **kwargs)
            except (ClientError, WaiterError) as e:
                if isinstance(e, ClientError):
                    error_code = e.response['Error']['Code']
                elif isinstance(e, WaiterError):
                    error_code = e.last_response['Error']['Code']
                else:
                    raise
                if error_code in ['Throttling', 'RequestLimitExceeded']:
                    logging.warn('AWS API Limiting error: {}'.format(error_code))
                    logging.warn('Sleeping for {} seconds before retrying'.format(local_wait))
                    time_to_next = next_time - time.time()
                    if time_to_next > 0:
                        time.sleep(time_to_next)
                    else:
                        local_timeout += time_to_next
                    local_timeout -= local_wait
                    local_wait *= 2
                    continue
                raise
        raise Exception('Rate-limit timeout encountered waiting for {}'.format(boto_fn.__name__))
    return ignore_rate_errors


def wait_for_pong(url, timeout):
    """continually GETs /ping expecting JSON pong:true return
    Does not stop on exception as connection error may be expected
    """
    @retrying.retry(wait_fixed=3000, stop_max_delay=timeout * 1000)
    def ping_app():
        logging.info('Attempting to ping test application')
        r = requests.get('http://{}/ping'.format(url), timeout=10)
        assert r.ok, 'Bad response from test server: ' + str(r.status_code)
        assert r.json() == {"pong": True}, 'Unexpected response from server: ' + repr(r.json())
    ping_app()


def wait_for_len(fetch_fn, target_count, timeout):
    """Will call fetch_fn, get len() on the result and repeat until it is
    equal to target count or timeout (in seconds) has been reached
    """
    @retrying.retry(wait_fixed=3000, stop_max_delay=timeout * 1000,
                    retry_on_result=lambda res: res is False,
                    retry_on_exception=lambda ex: False)
    def check_for_match():
        items = fetch_fn()
        count = len(items)
        logging.info('Waiting for len()=={}. Current count: {}. Items: {}'.format(target_count, count, repr(items)))
        if count != target_count:
            return False
    check_for_match()


def session_tempfile(data):
    """Writes bites to a named temp file and returns its path
    the temp file will be removed when the interpreter exits
    """
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        temp_path = f.name

    def remove_file():
        if os.path.exists(temp_path):
            os.remove(temp_path)

    # Attempt to remove the file upon normal interpreter exit.
    atexit.register(remove_file)
    return temp_path
