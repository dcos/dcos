import logging
from collections import namedtuple

import requests
import retrying

Host = namedtuple('Host', ['private_ip', 'public_ip'])
SshInfo = namedtuple('SshInfo', ['user', 'home_dir'])


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
