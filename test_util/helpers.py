"""Various helpers for test runners and integration testing directly
"""
import copy
import logging
import time
from collections import namedtuple
from functools import wraps

import requests
import retrying
from botocore.exceptions import ClientError, WaiterError

import test_util

Host = namedtuple('Host', ['private_ip', 'public_ip'])
SshInfo = namedtuple('SshInfo', ['user', 'home_dir'])


class DcosUser:
    """A lightweight user representation."""
    def __init__(self, auth_json):
        self.auth_json = auth_json
        self.auth_header = {}
        self.auth_token = None
        self.auth_cookie = None

    def authenticate(self, cluster):
        assert isinstance(cluster, test_util.cluster_api.ClusterApi), 'Unrecognized cluster object!'
        logging.info('Attempting authentication')
        r = cluster.post(path='/acs/api/v1/auth/login', user=None, json=self.auth_json)
        r.raise_for_status()
        logging.info('Received authorization blob: {}'.format(r.json()))
        assert r.ok, 'Authentication failed with status_code: {}'.format(r.status_code)
        self.auth_token = r.json()['token']
        self.auth_header = {'Authorization': 'token={}'.format(self.auth_token)}
        self.auth_cookie = r.cookies['dcos-acs-auth-cookie']
        logging.info('Authentication successful')


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
        logging.info('Waiting for len({})=={}. Current count: {}. Items: {}'.format(
            fetch_fn.__name__, target_count, count, repr(items)))
        if count != target_count:
            return False
    check_for_match()
