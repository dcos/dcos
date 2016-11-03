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

ADMINROUTER_PORT_MAPPING = {
    'master': {'http': 80, 'https': 443},
    'agent': {'http': 61001, 'https': 61002}}


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


class ApiClient:

    def __init__(self, cluster, user, api_base, default_headers=None, ca_cert_path=None):
        self.cluster = cluster
        self.user = user
        self.api_base = api_base
        if default_headers is None:
            default_headers = dict()
        self.default_headers = default_headers
        self.ca_cert_path = ca_cert_path

    def api_request(self, method, path, node=None, port=None, **kwargs):
        """
        Makes a request with default headers + user auth headers if necessary
        If DCOS_CA_CERT_PATH is set in environment, this method will pass it to requests
        Args:
            method: (str) name of method for requests.request
            node: see get_url()
            path: see get_url()
            port: see get_url()
            **kwargs: any optional arguments to be passed to requests.request
        """
        headers = copy.copy(self.default_headers)
        if self.cluster.auth_enabled and self.cluster.web_auth_default_user:
            headers.update(self.cluster.web_auth_default_user.auth_header)

        if self.ca_cert_path:
            kwargs['verify'] = self.ca_cert_path

        headers.update(kwargs.pop('headers', {}))
        url = self.get_url(node=node, path=path, port=port)
        logging.info('Request method {}: {}'.format(method, url))
        logging.debug('Reqeust kwargs: {}'.format(kwargs))
        logging.debug('Request headers: {}'.format(headers))
        return requests.request(method, url, headers=headers, **kwargs)

    def get_url(self, node, path, port=None):
        """
        Args:
            path: (str) URL path to request if self.api_base is set it will be prepended
            node: (str) the hostname of the node to be requested from, if node=None,
                then public cluster address (see environment DCOS_DNS_ADDRESS)
            port: (int) port to be requested at. If port=None, the default port
                for that given node type will be used
        Returns:
            fully-qualified URL string for this API
        """
        if node is None:
            node = self.cluster.dns_host
            role = 'master'
        else:
            if node in self.cluster.masters:
                role = 'master'
            elif node in self.cluster.all_slaves:
                role = 'agent'
            else:
                raise Exception('Node {} is not recognized within the DC/OS cluster'.format(node))

        if self.api_base:
            path = '{}/{}'.format(self.api_base.rstrip('/'), path.lstrip('/'))

        if port is None:
            port = ADMINROUTER_PORT_MAPPING[role][self.cluster.scheme]

        if (port == 80 and self.cluster.scheme == 'http') or (port == 443 and self.cluster.scheme == 'https'):
            netloc = node
        else:
            netloc = '{}:{}'.format(node, port)

        return '{}://{}/{}'.format(self.cluster.scheme, netloc, path.lstrip('/'))

    get = functools.partialmethod(api_request, 'get')
    post = functools.partialmethod(api_request, 'post')
    put = functools.partialmethod(api_request, 'put')
    delete = functools.partialmethod(api_request, 'delete')
    options = functools.partialmethod(api_request, 'options')
    head = functools.partialmethod(api_request, 'head')
    patch = functools.partialmethod(api_request, 'patch')
    delete = functools.partialmethod(api_request, 'delete')


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
