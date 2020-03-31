# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import copy
import logging
import time

import pytest
import requests

from generic_test_code.common import ping_mesos_agent, verify_header
from mocker.endpoints.marathon import (
    SCHEDULER_APP_ALWAYSTHERE,
    SCHEDULER_APP_ALWAYSTHERE_DIFFERENTPORT,
)
from mocker.endpoints.mesos import AGENT1_ID, EXTRA_AGENT_DICT
from runner.common import CACHE_FIRST_POLL_DELAY, Vegeta
from util import GuardedSubprocess, LineBufferFilter, SearchCriteria

log = logging.getLogger(__name__)


class TestCache:
    def test_if_first_cache_refresh_occurs_earlier(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Executing cache refresh triggered by timer': SearchCriteria(1, False),
            r'Cache `[\s\w]+` empty. Fetching.': SearchCriteria(3, True),
            'Updated Mesos state cache': SearchCriteria(1, True),
            'Updated Marathon apps cache': SearchCriteria(1, True),
            'Updated marathon leader cache': SearchCriteria(1, True),
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
            r'Cache `[\s\w]+` expired. Refresh.': SearchCriteria(8, True),
            'Updated Mesos state cache': SearchCriteria(3, True),
            'Updated Marathon apps cache': SearchCriteria(3, True),
            'Updated marathon leader cache': SearchCriteria(3, True),
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

        # In total, we should get three cache updates in given time frame plus
        # one NOOP due to cache not being expired yet:
        timeout = cache_poll_period * 3 + 1

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
            r'Cache `[\s\w]+` empty. Fetching.': SearchCriteria(3, True),
            'Updated Mesos state cache': SearchCriteria(1, True),
            'Updated Marathon apps cache': SearchCriteria(1, True),
            'Updated marathon leader cache': SearchCriteria(1, True),
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
            'Updated Mesos state cache':
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
            'Updated Mesos state cache':
                SearchCriteria(2, False),
            'Cache entry `svcapps` is stale':
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
            'Updated Marathon apps cache':
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
            'Updated Marathon apps cache':
                SearchCriteria(2, False),
            'Cache entry `mesosstate` is stale':
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
            'Updated Mesos state cache':
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
            'Updated Marathon apps cache': SearchCriteria(1, True),
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
                             agent_id=EXTRA_AGENT_DICT['id'],
                             expect_status=404)

            mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                func_name='enable_extra_agent')

            # First poll (2s) + normal poll interval(4s) < 2 * normal poll
            # interval(4s)
            time.sleep(cache_poll_period * 2)

            ping_mesos_agent(ar,
                             valid_user_header,
                             agent_id=EXTRA_AGENT_DICT['id'],
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
            assert resp.status_code == 503

    def test_if_absence_of_agent_is_handled_by_cache(
            self, nginx_class, mocker, valid_user_header):

        ar = nginx_class()

        with GuardedSubprocess(ar):
            ping_mesos_agent(
                ar,
                valid_user_header,
                agent_id='bdcd424a-b59e-4df4-b492-b54e38926bd8-S0',
                expect_status=404)

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
            'Cannot decode marathon leader JSON': SearchCriteria(1, True),
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
        agent_id = AGENT1_ID
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

    # This test can succed 40-50% number of times if we remove the fix. Hence
    # we re-run it here 5 times.
    @pytest.mark.parametrize('execution_number', range(5))
    def test_if_mesos_leader_failover_is_followed_by_cache_http(
            self,
            nginx_class,
            valid_user_header,
            mocker,
            dns_server_mock,
            execution_number):
        # Nginx resolver enforces 5s (grep for `resolver ... valid=Xs`), so it
        # is VERY important to use cache pool period of >5s.
        cache_poll_period = 8
        ar = nginx_class(
            cache_poll_period=cache_poll_period,
            cache_expiration=cache_poll_period - 1,
            upstream_mesos="http://leader.mesos:5050",
            )

        # Enable recording for Mesos mocks:
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')
        mocker.send_command(endpoint_id='http://127.0.0.3:5050',
                            func_name='record_requests')
        dns_server_mock.set_dns_entry('leader.mesos.', ip="127.0.0.2", ttl=2)
        with GuardedSubprocess(ar):
            # Force cache refresh early, so that we do not have to wait too
            # long
            ping_mesos_agent(ar,
                             valid_user_header,
                             agent_id=EXTRA_AGENT_DICT['id'],
                             expect_status=404)

            dns_server_mock.set_dns_entry('leader.mesos.', ip="127.0.0.3", ttl=2)

            # First poll, request triggered (0s) + normal poll interval(6s)
            # interval(6s) + 2
            time.sleep(cache_poll_period + 2)

        mesosmock_pre_reqs = mocker.send_command(
            endpoint_id='http://127.0.0.2:5050',
            func_name='get_recorded_requests')
        mesosmock_post_reqs = mocker.send_command(
            endpoint_id='http://127.0.0.3:5050',
            func_name='get_recorded_requests')
        assert len(mesosmock_pre_reqs) == 1
        assert len(mesosmock_post_reqs) == 1


class TestCacheMesosLeader:
    def test_if_unset_hostip_var_is_handled(self, nginx_class, valid_user_header):
        filter_regexp = {
            ('Private IP address of the host is unknown, '
                'aborting cache-entry creation for mesos leader'):
                    SearchCriteria(1, True),
            'Updated mesos leader cache':
                SearchCriteria(1, True),
        }
        ar = nginx_class(host_ip=None)

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)
            # Just trigger the cache update:
            ping_mesos_agent(ar, valid_user_header)

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    def test_if_missing_mesos_leader_entry_is_handled(
            self, nginx_class, valid_user_header, dns_server_mock):
        filter_regexp = {
            'Failed to instantiate the resolver': SearchCriteria(0, True),
            'DNS server returned error code': SearchCriteria(1, True),
            'Updated mesos leader cache':
                SearchCriteria(0, True),
        }

        ar = nginx_class()

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)
            # Unfortunatelly there are upstreams that use `leader.mesos` and
            # removing this entry too early will result in Nginx failing to start.
            # So we need to do it right after nginx starts, but before first
            # cache update.
            time.sleep(1)
            dns_server_mock.remove_dns_entry('leader.mesos.')

            # Now let's trigger the cache update:
            ping_mesos_agent(ar, valid_user_header)

            lbf.scan_log_buffer()

            assert lbf.extra_matches == {}

    def test_if_mesos_leader_locality_is_resolved(
            self, nginx_class, valid_user_header, dns_server_mock):
        cache_poll_period = 4
        nonlocal_leader_ip = "127.0.0.3"
        local_leader_ip = "127.0.0.2"
        filter_regexp_pre = {
            'Failed to instantiate the resolver': SearchCriteria(0, True),
            'mesos leader is non-local: `{}`'.format(nonlocal_leader_ip):
                SearchCriteria(1, True),
            ('Private IP address of the host is unknown, '
                'aborting cache-entry creation for mesos leader'):
                    SearchCriteria(0, True),
            'Updated mesos leader cache':
                SearchCriteria(1, True),
        }
        filter_regexp_post = {
            'Failed to instantiate the resolver': SearchCriteria(0, True),
            'mesos leader is local': SearchCriteria(1, True),
            ('Private IP address of the host is unknown, '
                'aborting cache-entry creation for mesos leader'):
                    SearchCriteria(0, True),
            'Updated mesos leader cache':
                SearchCriteria(1, True),
        }

        dns_server_mock.set_dns_entry('leader.mesos.', ip=nonlocal_leader_ip)

        ar = nginx_class(cache_poll_period=cache_poll_period, cache_expiration=3)

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp_pre,
                                   line_buffer=ar.stderr_line_buffer)
            # Just trigger the cache update:
            ping_mesos_agent(ar, valid_user_header)

            lbf.scan_log_buffer()

            assert lbf.extra_matches == {}

            dns_server_mock.set_dns_entry('leader.mesos.', ip=local_leader_ip)

            # First poll (2s) + normal poll interval(4s) < 2 * normal poll
            # interval(4s)
            time.sleep(cache_poll_period * 2)

            lbf = LineBufferFilter(filter_regexp_post,
                                   line_buffer=ar.stderr_line_buffer)
            # Just trigger the cache update:
            ping_mesos_agent(ar, valid_user_header)

            lbf.scan_log_buffer()

            assert lbf.extra_matches == {}

    def test_if_backend_requests_have_useragent_set_correctly(
            self, nginx_class, mocker, valid_user_header):
        # Enable recording for marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='record_requests')
        # Enable recording for Mesos
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')

        # Make regular polling occur later than usual, so that we get a single
        # cache refresh:
        ar = nginx_class(cache_poll_period=60, cache_expiration=55)

        with GuardedSubprocess(ar):
            # Initiate cache refresh by issuing a request:
            ping_mesos_agent(ar, valid_user_header)

        mesos_requests = mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                             func_name='get_recorded_requests')
        marathon_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                                func_name='get_recorded_requests')

        assert len(mesos_requests) == 1
        assert len(marathon_requests) == 2

        # We could use a loop here, but let's make it a bit easier to debug:
        verify_header(mesos_requests[0]['headers'],
                      'User-Agent',
                      'Master Admin Router')
        verify_header(marathon_requests[0]['headers'],
                      'User-Agent',
                      'Master Admin Router')
        verify_header(marathon_requests[1]['headers'],
                      'User-Agent',
                      'Master Admin Router')


class TestCacheMarathon:
    @pytest.mark.parametrize('host_port', [12345, 0, None])
    def test_app_with_container_networking_and_defined_container_port(
            self, nginx_class, mocker, valid_user_header, host_port):
        # Testing the case when a non-zero container port is specified
        # in Marathon app definition with networking mode 'container'.
        # It does not matter if the host port is fixed (non-zero),
        # randomly assigned by Marathon (0) or is not present at all:
        # Admin Router must route the request to the specified container port.
        app = self._scheduler_alwaysthere_app()
        app['networks'] = [{
            'mode': 'container',
            'name': 'samplenet'
        }]
        if host_port is not None:
            app['container']['portMappings'] = [{'containerPort': 80, 'hostPort': host_port}]
        else:
            app['container']['portMappings'] = [{'containerPort': 80}]
        app['tasks'][0]['ipAddresses'][0]['ipAddress'] = '127.0.0.2'

        ar = nginx_class()

        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": [app]})

        url = ar.make_url_from_path('/service/scheduler-alwaysthere/foo/bar/')
        with GuardedSubprocess(ar):
            # Trigger cache update by issuing request:
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)

            assert resp.status_code == 200
            req_data = resp.json()
            assert req_data['endpoint_id'] == 'http://127.0.0.2:80'

    @pytest.mark.parametrize('host_port', [12345, 0, None])
    def test_app_with_container_networking_and_random_container_port(
            self, nginx_class, mocker, valid_user_header, host_port):
        # Testing the case when container port is specified as 0
        # in Marathon app definition with networking mode 'container'.
        # This means that the Marathon app container port is randomly assigned
        # by Marathon. We are reusing port 16000 on 127.0.0.1 exposed by the
        # mock server, as the one randomly chosen by Marathon.
        # It does not matter if the host port is fixed (non-zero),
        # randomly assigned by Marathon (0) or is not present at all:
        # Admin Router must route the request to the specified container port.
        app = self._scheduler_alwaysthere_app()
        app['networks'] = [{
            'mode': 'container',
            'name': 'samplenet'
        }]
        if host_port is not None:
            app['container']['portMappings'] = [{'containerPort': 0, 'hostPort': host_port}]
        else:
            app['container']['portMappings'] = [{'containerPort': 0}]
        app['tasks'][0]['ipAddresses'][0]['ipAddress'] = '127.0.0.1'
        app['tasks'][0]['ports'][0] = '16000'

        ar = nginx_class()

        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": [app]})

        url = ar.make_url_from_path('/service/scheduler-alwaysthere/foo/bar/')
        with GuardedSubprocess(ar):
            # Trigger cache update by issuing request:
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)

            assert resp.status_code == 200
            req_data = resp.json()
            assert req_data['endpoint_id'] == 'http://127.0.0.1:16000'

    @pytest.mark.parametrize(
        'networking_mode, container_port',
        [['container/bridge', '80'], ['container/bridge', '0'], ['host', '80'], ['host', '0']]
        )
    def test_app_with_bridge_and_host_networking(
            self, nginx_class, mocker, valid_user_header, container_port, networking_mode):
        # Testing the cases when networking mode is either 'container' or 'host'.
        # The host port can be non-zero or 0. In the latter case Marathon will
        # randomly choose the host port. For simplicity in this test we are
        # reusing port 16000 on 127.0.0.1 exposed by the mock server, as both
        # the fixed (non-zero) one and the one randomly chosen by Marathon.
        # It does not matter if the container port is fixed (non-zero) or
        # randomly assigned by Marathon (0) or: Admin Router must route the
        # request to the host port.
        app = self._scheduler_alwaysthere_app()
        app['networks'] = [{
            'mode': networking_mode
        }]

        app['container']['portMappings'] = [
            {'containerPort': container_port, 'hostPort': 16000}]
        app['tasks'][0]['ipAddresses'][0]['ipAddress'] = '127.0.0.1'

        ar = nginx_class()

        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": [app]})

        url = ar.make_url_from_path('/service/scheduler-alwaysthere/foo/bar/')
        with GuardedSubprocess(ar):
            # Trigger cache update by issuing request:
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)

            assert resp.status_code == 200
            req_data = resp.json()
            assert req_data['endpoint_id'] == 'http://127.0.0.1:16000'

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
            expected = "503 Service Unavailable: invalid Marathon svcapps cache"
            assert expected == resp.content.decode('utf-8').strip()
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

    def test_app_container_networking_with_invalid_port_mapping_index_label(
            self, nginx_class, mocker, valid_user_header):
        app = self._scheduler_alwaysthere_app()
        app["labels"]["DCOS_SERVICE_PORT_INDEX"] = "1"
        app['networks'] = [{'mode': 'container', 'name': 'samplenet'}]
        app['container']['portMappings'] = [{'containerPort': 16000, 'hostPort': 16000}]

        message = (
            "Cannot find port in container portMappings at Marathon "
            "port index '1' for app '{app_id}'"
        ).format(app_id=app["id"])
        filter_regexp = {message: SearchCriteria(1, True)}
        self._assert_filter_regexp_for_invalid_app(
            filter_regexp, app, nginx_class, mocker, valid_user_header)

    def test_app_container_networking_with_invalid_task_port_index_label(
            self, nginx_class, mocker, valid_user_header):
        app = self._scheduler_alwaysthere_app()
        app["labels"]["DCOS_SERVICE_PORT_INDEX"] = "1"
        app['networks'] = [{'mode': 'container', 'name': 'samplenet'}]
        app['container']['portMappings'] = [
            {'containerPort': 7777, 'hostPort': 16000},
            {'containerPort': 0},
        ]

        message = (
            "Cannot find port in task ports at Marathon "
            "port index '1' for app '{app_id}'"
        ).format(app_id=app["id"])
        filter_regexp = {message: SearchCriteria(1, True)}
        self._assert_filter_regexp_for_invalid_app(
            filter_regexp, app, nginx_class, mocker, valid_user_header)

    @pytest.mark.parametrize('networking_mode', ['container/bridge', 'host'])
    def test_app_networking_with_invalid_task_port_index_label(
            self, nginx_class, mocker, valid_user_header, networking_mode):
        app = self._scheduler_alwaysthere_app()
        app["labels"]["DCOS_SERVICE_PORT_INDEX"] = "1"
        app['networks'] = [{'mode': networking_mode}]

        message = (
            "Cannot find port in task ports at Marathon "
            "port index '1' for app '{app_id}'"
        ).format(app_id=app["id"])
        filter_regexp = {message: SearchCriteria(1, True)}
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
            "Cannot find host or ip for app '{}'".format(app["id"]):
                SearchCriteria(1, True),
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
            nginx_class (Nginx): Nginx process fixture
            mocker (Mocker): Mocker fixture
            auth_header (dict): Headers that should be passed to Nginx in the
                request
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
            assert resp.status_code == 404

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    def _scheduler_alwaysthere_app(self):
        """Returns a valid Marathon app with the '/scheduler-alwaysthere' id"""
        return copy.deepcopy(SCHEDULER_APP_ALWAYSTHERE)
