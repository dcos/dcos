# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import copy
import logging
import time

import requests

from generic_test_code.common import ping_mesos_agent
from mocker.endpoints.marathon import (
    SCHEDULER_APP_ALWAYSTHERE,
    SCHEDULER_APP_ALWAYSTHERE_DIFFERENTPORT,
)
from mocker.endpoints.mesos import EXTRA_SLAVE_DICT, SLAVE1_ID
from runner.common import CACHE_FIRST_POLL_DELAY, Vegeta
from util import GuardedSubprocess, LineBufferFilter, SearchCriteria

log = logging.getLogger(__name__)


class TestCache:
    def test_if_first_cache_refresh_occurs_earlier(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Executing cache refresh triggered by timer': SearchCriteria(1, False),
            'Cache `[\s\w]+` empty. Fetching.': SearchCriteria(3, True),
            'Mesos state cache has been successfully updated': SearchCriteria(1, True),
            'Marathon apps cache has been successfully updated': SearchCriteria(1, True),
            'Marathon leader cache has been successfully updated': SearchCriteria(1, True),
            }
        # Enable recording for marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='record_requests')
        # Enable recording for Mesos
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')

        # Make regular polling occur later than usual, so that we get clear
        # results.
        ar = nginx_class(cache_poll_period=60, cache_expiration=55)

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=(CACHE_FIRST_POLL_DELAY + 1),
                                   line_buffer=ar.stderr_line_buffer)

            lbf.scan_log_buffer()

            # Do a request that uses cache so that we can verify that data was
            # in fact cached and no more than one req to mesos/marathon
            # backends were made
            ping_mesos_agent(ar, valid_user_header)

        mesos_requests = mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                             func_name='get_recorded_requests')
        marathon_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                                func_name='get_recorded_requests')

        assert lbf.extra_matches == {}
        assert len(mesos_requests) == 1
        assert len(marathon_requests) == 2

    def test_if_cache_refresh_occurs_regularly(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Executing cache refresh triggered by timer': SearchCriteria(3, False),
            'Cache `[\s\w]+` expired. Refresh.': SearchCriteria(6, True),
            'Mesos state cache has been successfully updated': SearchCriteria(3, True),
            'Marathon apps cache has been successfully updated': SearchCriteria(3, True),
            'Marathon leader cache has been successfully updated': SearchCriteria(3, True),
            }
        cache_poll_period = 4

        # Enable recording for marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='record_requests')
        # Enable recording for mesos
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')

        # Make regular polling occur faster than usual to speed up the tests.
        ar = nginx_class(cache_poll_period=cache_poll_period, cache_expiration=3)

        # In total, we should get three cache updates in given time frame:
        timeout = CACHE_FIRST_POLL_DELAY + cache_poll_period * 2 + 1

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=timeout,
                                   line_buffer=ar.stderr_line_buffer)

            lbf.scan_log_buffer()

            # Do a request that uses cache so that we can verify that data was
            # in fact cached and no more than one req to mesos/marathon
            # backends were made
            ping_mesos_agent(ar, valid_user_header)

        mesos_requests = mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                             func_name='get_recorded_requests')
        marathon_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                                func_name='get_recorded_requests')

        assert lbf.extra_matches == {}
        assert len(mesos_requests) == 3
        assert len(marathon_requests) == 6

    def test_if_cache_refresh_is_triggered_by_request(
            self, nginx_class, mocker, valid_user_header):
        """...right after Nginx has started."""
        filter_regexp = {
            'Executing cache refresh triggered by request': SearchCriteria(1, True),
            'Cache `[\s\w]+` empty. Fetching.': SearchCriteria(3, True),
            'Mesos state cache has been successfully updated': SearchCriteria(1, True),
            'Marathon apps cache has been successfully updated': SearchCriteria(1, True),
            'Marathon leader cache has been successfully updated': SearchCriteria(1, True),
            }
        # Enable recording for marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='record_requests')
        # Enable recording for mesos
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')

        # Make sure that timers will not interfere:
        ar = nginx_class(cache_first_poll_delay=120,
                         cache_poll_period=120,
                         cache_expiration=115)

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=5,
                                   line_buffer=ar.stderr_line_buffer)

            ping_mesos_agent(ar, valid_user_header)
            lbf.scan_log_buffer()

            # Do an extra request so that we can verify that data was in fact
            # cached and no more than one req to mesos/marathon backends were
            # made
            ping_mesos_agent(ar, valid_user_header)

        mesos_requests = mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                             func_name='get_recorded_requests')
        marathon_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                                func_name='get_recorded_requests')

        assert lbf.extra_matches == {}
        assert len(mesos_requests) == 1
        assert len(marathon_requests) == 2

    def test_if_broken_marathon_causes_marathon_cache_to_expire_and_requests_to_fail(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Marathon app request failed: invalid response status: 500':
                SearchCriteria(1, False),
            'Mesos state cache has been successfully updated':
                SearchCriteria(2, False),
            'Cache entry `svcapps` is too old, aborting request':
                SearchCriteria(1, True),
        }

        ar = nginx_class(cache_max_age_soft_limit=3,
                         cache_max_age_hard_limit=4,
                         cache_expiration=2,
                         cache_poll_period=3,
                         )

        url = ar.make_url_from_path('/service/scheduler-alwaysthere/foo/bar/')

        with GuardedSubprocess(ar):
            # Register Line buffer filter:
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=5,  # Just to give LBF enough time
                                   line_buffer=ar.stderr_line_buffer)

            # Trigger cache update by issuing request:
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 200

            # Break marathon
            mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                func_name='always_bork',
                                aux_data=True)

            # Wait for the cache to be old enough to be discarded by AR:
            # cache_max_age_hard_limit + 1s for good measure
            # must be more than cache_poll_period
            time.sleep(4 + 1)

            # Perform the main/test request:
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 503

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    def test_if_temp_marathon_borkage_does_not_disrupt_caching(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Marathon app request failed: invalid response status: 500':
                SearchCriteria(1, False),
            'Mesos state cache has been successfully updated':
                SearchCriteria(2, False),
            'Using stale `svcapps` cache entry to fulfill the request':
                SearchCriteria(1, True),
        }

        ar = nginx_class(cache_max_age_soft_limit=3,
                         cache_max_age_hard_limit=1200,
                         cache_expiration=2,
                         cache_poll_period=3,
                         )

        url = ar.make_url_from_path('/service/scheduler-alwaysthere/foo/bar/')

        with GuardedSubprocess(ar):
            # Register Line buffer filter:
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=5,  # Just to give LBF enough time
                                   line_buffer=ar.stderr_line_buffer)

            # Trigger cache update by issuing request:
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 200

            # Break marathon
            mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                func_name='always_bork',
                                aux_data=True)

            # Wait for the cache to be old enough to be considered stale by AR:
            # cache_max_age_soft_limit + 1s for a good measure
            time.sleep(3 + 1)

            # Perform the main/test request:
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 200

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    def test_if_broken_mesos_causes_mesos_cache_to_expire_and_requests_to_fail(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Mesos state request failed: invalid response status: 500':
                SearchCriteria(1, False),
            'Marathon apps cache has been successfully updated':
                SearchCriteria(2, False),
            'Cache entry `mesosstate` is too old, aborting request':
                SearchCriteria(1, True),
        }

        ar = nginx_class(cache_poll_period=3,
                         cache_expiration=2,
                         cache_max_age_soft_limit=3,
                         cache_max_age_hard_limit=4,
                         )

        with GuardedSubprocess(ar):
            # Register Line buffer filter:
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=5,  # Just to give LBF enough time
                                   line_buffer=ar.stderr_line_buffer)

            # Trigger cache update using a request:
            ping_mesos_agent(ar, valid_user_header)

            # Break mesos
            mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                func_name='always_bork',
                                aux_data=True)

            # Wait for the cache to be old enough to be discarded by AR:
            # cache_max_age_hard_limit + 1s for good measure
            # must be more than cache_poll_period
            time.sleep(4 + 1)

            # Perform the main/test request:
            ping_mesos_agent(ar, valid_user_header, expect_status=503)

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    def test_if_temp_mesos_borkage_does_not_dirupt_caching(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Mesos state request failed: invalid response status: 500':
                SearchCriteria(1, False),
            'Marathon apps cache has been successfully updated':
                SearchCriteria(2, False),
            'Using stale `mesosstate` cache entry to fulfill the request':
                SearchCriteria(1, True),
        }

        ar = nginx_class(cache_poll_period=3,
                         cache_expiration=2,
                         cache_max_age_soft_limit=3,
                         cache_max_age_hard_limit=1800,
                         )

        with GuardedSubprocess(ar):
            # Register Line buffer filter:
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=5,  # Just to give LBF enough time
                                   line_buffer=ar.stderr_line_buffer)

            # Trigger cache update using a request:
            ping_mesos_agent(ar, valid_user_header)

            # Break mesos
            mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                func_name='always_bork',
                                aux_data=True)

            # Wait for the cache to be old enough to become stale:
            # cache_max_age_soft_limit + 1s for good measure
            time.sleep(3 + 1)

            # Perform the main/test request:
            ping_mesos_agent(ar, valid_user_header, expect_status=200)

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    def test_if_broken_marathon_does_not_break_mesos_cache(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Marathon app request failed: invalid response status: 500':
                SearchCriteria(1, True),
            'Mesos state cache has been successfully updated':
                SearchCriteria(1, True),
        }

        # Break marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='always_bork',
                            aux_data=True)

        ar = nginx_class()

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=(CACHE_FIRST_POLL_DELAY + 1),
                                   line_buffer=ar.stderr_line_buffer)

            ping_mesos_agent(ar, valid_user_header)
            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    def test_if_broken_mesos_does_not_break_marathon_cache(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Mesos state request failed: invalid response status: 500':
                SearchCriteria(1, True),
            'Marathon apps cache has been successfully updated': SearchCriteria(1, True),
        }

        # Break marathon
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='always_bork',
                            aux_data=True)

        ar = nginx_class()
        url = ar.make_url_from_path('/service/scheduler-alwaysthere/bar/baz')

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=(CACHE_FIRST_POLL_DELAY + 1),
                                   line_buffer=ar.stderr_line_buffer)

            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            lbf.scan_log_buffer()

        assert resp.status_code == 200
        req_data = resp.json()
        assert req_data['endpoint_id'] == 'http://127.0.0.1:16000'

        assert lbf.extra_matches == {}

    def test_if_changing_marathon_apps_is_reflected_in_cache(
            self, nginx_class, valid_user_header, mocker):
        cache_poll_period = 4
        ar = nginx_class(cache_poll_period=cache_poll_period, cache_expiration=3)
        url = ar.make_url_from_path('/service/scheduler-alwaysthere/bar/baz')

        with GuardedSubprocess(ar):
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 200
            req_data = resp.json()
            assert req_data['endpoint_id'] == 'http://127.0.0.1:16000'

            new_apps = {"apps": [SCHEDULER_APP_ALWAYSTHERE_DIFFERENTPORT, ]}
            mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                func_name='set_apps_response',
                                aux_data=new_apps)

            # First poll (2s) + normal poll interval(4s) < 2 * normal poll
            # interval(4s)
            time.sleep(cache_poll_period * 2)

            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 200
            req_data = resp.json()
            assert req_data['endpoint_id'] == 'http://127.0.0.15:16001'

    def test_if_changing_mesos_state_is_reflected_in_cache(
            self, nginx_class, valid_user_header, mocker):
        cache_poll_period = 4
        ar = nginx_class(cache_poll_period=cache_poll_period, cache_expiration=3)

        with GuardedSubprocess(ar):
            ping_mesos_agent(ar,
                             valid_user_header,
                             agent_id=EXTRA_SLAVE_DICT['id'],
                             expect_status=404)

            mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                func_name='enable_extra_slave')

            # First poll (2s) + normal poll interval(4s) < 2 * normal poll
            # interval(4s)
            time.sleep(cache_poll_period * 2)

            ping_mesos_agent(ar,
                             valid_user_header,
                             agent_id=EXTRA_SLAVE_DICT['id'],
                             endpoint_id='http://127.0.0.4:15003')

    def test_if_changing_marathon_leader_is_reflected_in_cache(
            self, nginx_class, mocker, valid_user_header):

        cache_poll_period = 4
        ar = nginx_class(cache_poll_period=cache_poll_period, cache_expiration=3)

        url = ar.make_url_from_path('/system/v1/leader/marathon/foo/bar/baz')

        with GuardedSubprocess(ar):
            # let's make sure that current leader is the default one
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 200
            req_data = resp.json()
            assert req_data['endpoint_id'] == 'http://127.0.0.2:80'

            # change the leader and wait for cache to notice
            mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                func_name='change_leader',
                                aux_data="127.0.0.3:80")
            # First poll (2s) + normal poll interval(4s) < 2 * normal poll
            # interval(4s)
            time.sleep(cache_poll_period * 2)

            # now, let's see if the leader changed
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 200
            req_data = resp.json()
            assert req_data['endpoint_id'] == 'http://127.0.0.3:80'

    def test_if_absence_of_marathon_leader_is_handled_by_cache(
            self, nginx_class, mocker, valid_user_header):

        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='remove_leader')

        ar = nginx_class()
        url = ar.make_url_from_path('/system/v1/leader/marathon/foo/bar/baz')

        with GuardedSubprocess(ar):
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 404

    def test_if_caching_works_for_mesos_state(
            self, nginx_class, mocker, valid_user_header):
        # Enable recording for mesos
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')

        ar = nginx_class()

        with GuardedSubprocess(ar):
            # Let the cache warm-up:
            time.sleep(CACHE_FIRST_POLL_DELAY + 1)
            for _ in range(3):
                ping_mesos_agent(ar, valid_user_header)

        mesos_requests = mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                             func_name='get_recorded_requests')

        # 3 requests + only one upstream request == cache works
        assert len(mesos_requests) == 1

    def test_if_caching_works_for_marathon_apps(
            self, nginx_class, mocker, valid_user_header):
        # Enable recording for marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='record_requests')
        # Enable recording for mesos
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')

        ar = nginx_class()
        url = ar.make_url_from_path('/service/scheduler-alwaysthere/bar/baz')

        with GuardedSubprocess(ar):
            # Let the cache warm-up:
            time.sleep(CACHE_FIRST_POLL_DELAY + 1)
            for _ in range(5):
                resp = requests.get(url,
                                    allow_redirects=False,
                                    headers=valid_user_header)
                assert resp.status_code == 200

        mesos_requests = mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                             func_name='get_recorded_requests')
        marathon_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                                func_name='get_recorded_requests')

        # 3 requests + only one upstream requst == cache works
        assert len(mesos_requests) == 1
        assert len(marathon_requests) == 2

    def test_if_caching_works_for_marathon_leader(
            self, nginx_class, mocker, valid_user_header):
        # Enable recording for marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='record_requests')

        ar = nginx_class()
        url = ar.make_url_from_path('/system/v1/leader/marathon/foo/bar/baz')

        with GuardedSubprocess(ar):
            # Let the cache warm-up:
            time.sleep(CACHE_FIRST_POLL_DELAY + 1)
            for _ in range(5):
                resp = requests.get(url,
                                    allow_redirects=False,
                                    headers=valid_user_header)
                assert resp.status_code == 200
                req_data = resp.json()
                assert req_data['endpoint_id'] == 'http://127.0.0.2:80'

        marathon_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                                func_name='get_recorded_requests')

        # 3 requests + only one upstream request == cache works
        assert len(marathon_requests) == 2

    def test_if_broken_response_from_marathon_is_handled(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Cannot decode Marathon leader JSON': SearchCriteria(1, True),
        }

        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='break_leader_reply')

        ar = nginx_class()
        url = ar.make_url_from_path('/system/v1/leader/marathon/foo/bar/baz')

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=(CACHE_FIRST_POLL_DELAY + 1),
                                   line_buffer=ar.stderr_line_buffer)
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            lbf.scan_log_buffer()

        assert resp.status_code == 503
        assert lbf.extra_matches == {}

    def test_if_failed_request_triggered_update_is_recovered_by_timers(
            self, nginx_class, valid_user_header, mocker, log_catcher):
        # The idea here is to make Backend a bit slow, so that AR is still able
        # to update cache on first request.

        first_poll_delay = 3
        poll_period = 3
        cache_expiration = 2

        # Take cache invalidation out of the picture
        ar = nginx_class(cache_first_poll_delay=first_poll_delay,
                         cache_poll_period=poll_period,
                         cache_expiration=cache_expiration,
                         cache_max_age_soft_limit=1200,
                         cache_max_age_hard_limit=1800,
                         )
        # Make mesos just a bit :)
        # It mus respond slower than backend_request_timeout
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='always_bork',
                            aux_data=True)

        with GuardedSubprocess(ar):
            start = time.time()

            # Let's break the cache by making it update against broken Mesos:
            ping_mesos_agent(ar, valid_user_header, expect_status=503)

            time.sleep(1)

            # Let's make sure that the brokerage is still there
            ping_mesos_agent(ar, valid_user_header, expect_status=503)

            # Healing hands!
            mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                func_name='always_bork',
                                aux_data=False)

            # Let' wait for first poll to refresh cache
            time.sleep(1 + (first_poll_delay - (time.time() - start)))

            # Verify that the cache is OK now
            ping_mesos_agent(ar, valid_user_header)

    def test_if_early_boot_stage_can_recover_from_a_bit_slow_backend(
            self, nginx_class, valid_user_header, mocker, log_catcher):
        # The idea here is to make Backend a bit slow, so that AR is still able
        # to update cache on first request.

        refresh_lock_timeout = 10
        backend_request_timeout = 5

        ar = nginx_class(cache_first_poll_delay=1,
                         cache_poll_period=3,
                         cache_expiration=2,
                         cache_max_age_soft_limit=1200,
                         cache_max_age_hard_limit=1800,
                         cache_backend_request_timeout=backend_request_timeout,
                         cache_refresh_lock_timeout=refresh_lock_timeout,
                         )
        agent_id = 'de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1'
        url = ar.make_url_from_path('/agent/{}/blah/blah'.format(agent_id))
        v = Vegeta(log_catcher, target=url, jwt=valid_user_header, rate=3)

        # Make mesos just a bit :)
        # It mus respond slower than backend_request_timeout
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='always_stall',
                            aux_data=backend_request_timeout * 0.3)

        with GuardedSubprocess(ar):
            with GuardedSubprocess(v):
                time.sleep(backend_request_timeout * 0.3 + 1)  # let it warm-up!
                ping_mesos_agent(ar, valid_user_header)


class TestCacheMarathon:

    def test_upstream_wrong_json(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            "Cannot decode Marathon apps JSON: ": SearchCriteria(1, True),
        }

        ar = nginx_class()

        # Set wrong non-json response content
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_encoded_response',
                            aux_data=b"wrong response")

        url = ar.make_url_from_path('/service/scheduler-alwaysthere/foo/bar/')
        with GuardedSubprocess(ar):
            # Register Line buffer filter:
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=5,  # Just to give LBF enough time
                                   line_buffer=ar.stderr_line_buffer)

            # Trigger cache update by issuing request:
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert "cache state is invalid" in resp.content.decode('utf-8')
            assert resp.status_code == 503

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    def test_app_without_labels(
            self, nginx_class, mocker, valid_user_header):
        app = self._scheduler_alwaysthere_app()
        app.pop("labels", None)

        filter_regexp = {
            "Labels not found in app '{}'".format(app["id"]): SearchCriteria(1, True),
        }
        self._assert_filter_regexp_for_invalid_app(
            filter_regexp, app, nginx_class, mocker, valid_user_header)

    def test_app_without_service_scheme_label(
            self, nginx_class, mocker, valid_user_header):
        app = self._scheduler_alwaysthere_app()
        app["labels"].pop("DCOS_SERVICE_SCHEME", None)

        filter_regexp = {
            "Cannot find DCOS_SERVICE_SCHEME for app '{}'".format(app["id"]):
                SearchCriteria(1, True),
        }

        self._assert_filter_regexp_for_invalid_app(
            filter_regexp, app, nginx_class, mocker, valid_user_header)

    def test_app_without_port_index_label(
            self, nginx_class, mocker, valid_user_header):
        app = self._scheduler_alwaysthere_app()
        app["labels"].pop("DCOS_SERVICE_PORT_INDEX", None)

        filter_regexp = {
            "Cannot find DCOS_SERVICE_PORT_INDEX for app '{}'".format(app["id"]):
                SearchCriteria(1, True),
        }
        self._assert_filter_regexp_for_invalid_app(
            filter_regexp, app, nginx_class, mocker, valid_user_header)

    def test_app_with_port_index_nan_label(
            self, nginx_class, mocker, valid_user_header):
        app = self._scheduler_alwaysthere_app()
        app["labels"]["DCOS_SERVICE_PORT_INDEX"] = "not a number"

        filter_regexp = {
            "Cannot convert port to number for app '{}'".format(app["id"]):
                SearchCriteria(1, True),
        }

        self._assert_filter_regexp_for_invalid_app(
            filter_regexp, app, nginx_class, mocker, valid_user_header)

    def test_app_without_mesos_tasks(
            self, nginx_class, mocker, valid_user_header):
        app = self._scheduler_alwaysthere_app()
        app["tasks"] = []

        filter_regexp = {
            "No task in state TASK_RUNNING for app '{}'".format(app["id"]):
                SearchCriteria(1, True),
        }

        self._assert_filter_regexp_for_invalid_app(
            filter_regexp, app, nginx_class, mocker, valid_user_header)

    def test_app_without_tasks_in_running_state(
            self, nginx_class, mocker, valid_user_header):
        app = self._scheduler_alwaysthere_app()
        app["tasks"] = [{"state": "TASK_FAILED"}]

        filter_regexp = {
            "No task in state TASK_RUNNING for app '{}'".format(app["id"]):
                SearchCriteria(1, True),
        }

        self._assert_filter_regexp_for_invalid_app(
            filter_regexp, app, nginx_class, mocker, valid_user_header)

    def test_app_without_task_host(
            self, nginx_class, mocker, valid_user_header):
        app = self._scheduler_alwaysthere_app()
        app["tasks"][0].pop("host", None)

        filter_regexp = {
            "Cannot find host for app '{}'".format(app["id"]):
                SearchCriteria(1, True),
        }

        self._assert_filter_regexp_for_invalid_app(
            filter_regexp, app, nginx_class, mocker, valid_user_header)

    def test_app_without_task_ports(
            self, nginx_class, mocker, valid_user_header):
        app = self._scheduler_alwaysthere_app()
        app["tasks"][0].pop("ports", None)

        filter_regexp = {
            "Cannot find ports for app '{}'".format(app["id"]):
                SearchCriteria(1, True),
        }

        self._assert_filter_regexp_for_invalid_app(
            filter_regexp, app, nginx_class, mocker, valid_user_header)

    def test_app_without_task_specified_port_idx(
            self, nginx_class, mocker, valid_user_header):
        app = self._scheduler_alwaysthere_app()
        app["labels"]["DCOS_SERVICE_PORT_INDEX"] = "5"

        filter_regexp = {
            "Cannot find port at Marathon port index '5' for app '{}'".format(
                app["id"]): SearchCriteria(1, True),
        }

        self._assert_filter_regexp_for_invalid_app(
            filter_regexp, app, nginx_class, mocker, valid_user_header)

    def _assert_filter_regexp_for_invalid_app(
            self,
            filter_regexp,
            app,
            nginx_class,
            mocker,
            auth_headers,
            ):
        """Helper method that will assert if provided regexp filter is found
        in nginx logs for given apps response from Marathon upstream endpoint.

        Arguments:
            filter_regexp (dict): Filter definition where key is the message
                looked up in logs and value is SearchCriteria definition
            app (dict): App that upstream endpoint should respond with
            nginx_class (Nginx): SCHEDULER fixture
            mocker (Mocker): Mocker fixture
            auth_header (dict): Headers that should be passed to SCHEDULER request
        """
        ar = nginx_class()

        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": [app]})

        # Remove all entries for mesos frameworks and mesos_dns so that
        # we test only the information in Marathon
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[])
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data=[])

        url = ar.make_url_from_path('/service/scheduler-alwaysthere/foo/bar/')
        with GuardedSubprocess(ar):
            # Register Line buffer filter:
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=5,  # Just to give LBF enough time
                                   line_buffer=ar.stderr_line_buffer)

            # Trigger cache update by issuing request:
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=auth_headers)
            assert resp.status_code == 500

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    def _scheduler_alwaysthere_app(self):
        """Returns a valid Marathon app with the '/scheduler-alwaysthere' id"""
        return copy.deepcopy(SCHEDULER_APP_ALWAYSTHERE)
