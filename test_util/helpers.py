"""Various helpers for test runners and integration testing directly
"""
import atexit
import copy
import functools
import logging
import os
import random
import string
import tempfile
import time
from collections import namedtuple
from typing import Union
from urllib.parse import urlsplit, urlunsplit

import pytest

import requests
import retrying
from botocore.exceptions import ClientError, WaiterError

Host = namedtuple('Host', ['private_ip', 'public_ip'])
SshInfo = namedtuple('SshInfo', ['user', 'home_dir'])

log = logging.getLogger(__name__)


# Token valid until 2036 for user albert@bekstil.net
#    {
#        "email": "albert@bekstil.net",
#        "email_verified": true,
#        "iss": "https://dcos.auth0.com/",
#        "sub": "google-oauth2|109964499011108905050",
#        "aud": "3yF5TOSzdlI45Q1xspxzeoGBe9fNxm9m",
#        "exp": 2090884974,
#        "iat": 1460164974
#    }

CI_CREDENTIALS = {'token': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImtpZCI6Ik9UQkVOakZFTWtWQ09VRTRPRVpGTlRNMFJrWXlRa015Tnprd1JrSkVRemRCTWpBM1FqYzVOZyJ9.eyJlbWFpbCI6ImFsYmVydEBiZWtzdGlsLm5ldCIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJpc3MiOiJodHRwczovL2Rjb3MuYXV0aDAuY29tLyIsInN1YiI6Imdvb2dsZS1vYXV0aDJ8MTA5OTY0NDk5MDExMTA4OTA1MDUwIiwiYXVkIjoiM3lGNVRPU3pkbEk0NVExeHNweHplb0dCZTlmTnhtOW0iLCJleHAiOjIwOTA4ODQ5NzQsImlhdCI6MTQ2MDE2NDk3NH0.OxcoJJp06L1z2_41_p65FriEGkPzwFB_0pA9ULCvwvzJ8pJXw9hLbmsx-23aY2f-ydwJ7LSibL9i5NbQSR2riJWTcW4N7tLLCCMeFXKEK4hErN2hyxz71Fl765EjQSO5KD1A-HsOPr3ZZPoGTBjE0-EFtmXkSlHb1T2zd0Z8T5Z2-q96WkFoT6PiEdbrDA-e47LKtRmqsddnPZnp0xmMQdTr2MjpVgvqG7TlRvxDcYc-62rkwQXDNSWsW61FcKfQ-TRIZSf2GS9F9esDF4b5tRtrXcBNaorYa9ql0XAWH5W_ct4ylRNl3vwkYKWa4cmPvOqT5Wlj9Tf0af4lNO40PQ'}     # noqa


def path_join(p1: str, p2: str):
    """Helper to ensure there is only one '/' between two strings"""
    return '{}/{}'.format(p1.rstrip('/'), p2.lstrip('/'))


class Url:
    """URL abstraction to allow convenient substitution of URL anatomy
    without having to copy and dissect the entire original URL
    """
    def __init__(self, scheme: str, host: str, path: str, query: str,
                 fragment: str, port: Union[str, int]):
        """{scheme}://{host}:{port}/{path}?{query}#{fragment}
        """
        self.scheme = scheme
        self.host = host
        self.path = path
        self.query = query
        self.fragment = fragment
        self.port = port

    @classmethod
    def from_string(cls, url_str: str):
        u = urlsplit(url_str)
        if ':' in u.netloc:
            host, port = u.netloc.split(':')
        else:
            host = u.netloc
            port = None
        return cls(u.scheme, host, u.path, u.query, u.fragment, port)

    @property
    def netloc(self):
        return '{}:{}'.format(self.host, self.port) if self.port else self.host

    def __str__(self):
        return urlunsplit((
            self.scheme,
            self.netloc,
            self.path,
            self.query if self.query else '',
            self.fragment if self.fragment else ''))

    def copy(self, scheme=None, host=None, path=None, query=None, fragment=None, port=None):
        """return new Url with any component replaced
        """
        return Url(
            scheme if scheme is not None else self.scheme,
            host if host is not None else self.host,
            path if path is not None else self.path,
            query if query is not None else self.query,
            fragment if fragment is not None else self.fragment,
            port if port is not None else self.port)


class ApiClientSession:
    """This class functions like the requests.session interface but adds
    a default Url and a request wrapper. This class only differs from requests.Session
    in that the cookies are cleared after each request (but not purged from the response)
    so that the request state may be more well-defined betweens tests sharing this object
    """
    def __init__(self, default_url: Url):
        """
        Args:
            default_url: Url object to wihch requests can be made
        """
        self.default_url = default_url
        self.session = requests.Session()

    def api_request(self, method, path_extension, *, scheme=None, host=None, query=None,
                    fragment=None, port=None, **kwargs) -> requests.Response:
        """ Direct wrapper for requests.session.request. This method is kept deliberatly
        simple so that child classes can alter this behavior without much copying

        Args:
            method: the HTTP verb
            path_extension: the extension to the path that is set as the default Url
            scheme: scheme to be used instead of that included with self.default_url
            host: host to be used instead of that included with self.default_url
            query: query to be used instead of that included with self.default_url
            fragment: fragment to be used instead of that included with self.default_url
            port: port to be used instead of that included with self.default_url

        Keyword Args:
            **kwargs: anything that can be passed to requests.request

        Returns:
            requests.Response
        """

        final_path = path_join(self.default_url.path, path_extension)

        request_url = str(self.default_url.copy(
            scheme=scheme,
            host=host,
            path=final_path,
            query=query,
            fragment=fragment,
            port=port))

        log.debug('Request method {}: {}. Arguments: {}'.format(method, request_url, repr(kwargs)))
        r = self.session.request(method, request_url, **kwargs)
        self.session.cookies.clear()
        return r

    @functools.wraps(api_request)
    def get(self, *args, **kwargs):
        return self.api_request('GET', *args, **kwargs)

    @functools.wraps(api_request)
    def post(self, *args, **kwargs):
        return self.api_request('POST', *args, **kwargs)

    @functools.wraps(api_request)
    def put(self, *args, **kwargs):
        return self.api_request('PUT', *args, **kwargs)

    @functools.wraps(api_request)
    def patch(self, *args, **kwargs):
        return self.api_request('PATCH', *args, **kwargs)

    @functools.wraps(api_request)
    def delete(self, *args, **kwargs):
        return self.api_request('DELETE', *args, **kwargs)

    @functools.wraps(api_request)
    def head(self, *args, **kwargs):
        return self.api_request('HEAD', *args, **kwargs)

    @functools.wraps(api_request)
    def options(self, *args, **kwargs):
        return self.api_request('OPTIONS', *args, **kwargs)


def is_retryable_exception(exception: Exception) -> bool:
    """ Helper method to catch HTTP errors that are likely safe to retry.
    Args:
        exception: exception raised from ApiClientSession.api_request instance
    """
    for ex in [requests.exceptions.ConnectionError, requests.exceptions.Timeout]:
        if isinstance(exception, ex):
            return True
    return False


class RetryCommonHttpErrorsMixin:
    """ Mixin for ApiClientSession so that random disconnects from network
    instability do not derail entire scripts. This functionality is configured
    through the retry_timeout keyword
    """
    def api_request(self, *args, retry_timeout: int=60, **kwargs) -> requests.Response:
        """ Adds 'retry_timeout' keyword to API requests.
        Args:
            *args: args to be passed to super()'s api_request method
            **kwargs: keyword args to be passed to super()'s api_request method
            retry_timeout: total number of seconds to keep retrying after
                the initial exception was raised
        """
        @retrying.retry(
            stop_max_delay=retry_timeout * 1000,
            retry_on_exception=is_retryable_exception)
        def retry_errors():
            try:
                return super(RetryCommonHttpErrorsMixin, self).api_request(*args, **kwargs)
            except:
                log.exception('Retrying common HTTP error...')
                raise

        return retry_errors()


def retry_boto_rate_limits(boto_fn, wait=2, timeout=60 * 60):
    """Decorator to make boto functions resilient to AWS rate limiting and throttling.
    If one of these errors is encounterd, the function will sleep for a geometrically
    increasing amount of time
    """
    @functools.wraps(boto_fn)
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
                    log.warn('AWS API Limiting error: {}'.format(error_code))
                    log.warn('Sleeping for {} seconds before retrying'.format(local_wait))
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
        log.info('Attempting to ping test application')
        r = requests.get('http://{}/ping'.format(url), timeout=10)
        r.raise_for_status()
        assert r.json() == {"pong": True}, 'Unexpected response from server: ' + repr(r.json())
    ping_app()


def session_tempfile(data):
    """Writes bytes to a named temp file and returns its path
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


def marathon_app_id_to_mesos_dns_subdomain(app_id):
    """Return app_id's subdomain as it would appear in a Mesos DNS A record.

    >>> marathon_app_id_to_mesos_dns_subdomain('/app-1')
    'app-1'
    >>> marathon_app_id_to_mesos_dns_subdomain('app-1')
    'app-1'
    >>> marathon_app_id_to_mesos_dns_subdomain('/group-1/app-1')
    'app-1-group-1'

    """
    return '-'.join(reversed(app_id.strip('/').split('/')))


def random_id(n):
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(n))


def skip_test_if_dcos_journald_log_disabled(dcos_api_session):
    response = dcos_api_session.get('/dcos-metadata/ui-config.json').json()
    try:
        strategy = response['uiConfiguration']['plugins']['mesos']['logging-strategy']
    except Exception:
        log.error('Unable to find logging strategy')
        raise
    if not strategy.startswith('journald'):
        pytest.skip('Skipping a test since journald logging is disabled')
