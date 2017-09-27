# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import time

import pytest

from generic_test_code.common import (
    generic_correct_upstream_dest_test,
    ping_mesos_agent,
)
from mocker.endpoints.mesos import AGENT_EXTRA_ID
from util import GuardedSubprocess


class TestNginxResolver:

    # In order to test that TTL of the DNS entry is indeed ignored/overriden,
    # we set this to a very high value. If `valid` argument has been properly
    # set for the resolver config option, then tests will pass
    LONG_TTL = 120

    @pytest.mark.parametrize("path,dest_port",
                             [("/system/v1/leader/mesos/foo/bar", 80),
                              ("/mesos/reflect/me", 5050),
                              ])
    def test_mesos_leader_reresolve_in_proxy_pass(
            self,
            nginx_class,
            valid_user_header,
            dns_server_mock,
            path,
            dest_port,
            ):
        # Change the TTL of `leader.mesos.` entry
        dns_server_mock.set_dns_entry(
            'leader.mesos.', ip='127.0.0.2', ttl=self.LONG_TTL)

        ar = nginx_class(upstream_mesos="http://leader.mesos:5050")
        with GuardedSubprocess(ar):
            generic_correct_upstream_dest_test(
                ar,
                valid_user_header,
                path,
                "http://127.0.0.2:{}".format(dest_port),
                )

            # Update the `leader.mesos.` entry with new value
            dns_server_mock.set_dns_entry(
                'leader.mesos.', ip='127.0.0.3', ttl=self.LONG_TTL)
            # This should be equal to 1.5 times the value of `valid=` DNS TTL
            # override in `resolver` config option -> 5s * 1.5 = 7.5s
            time.sleep(5 * 1.5)

            generic_correct_upstream_dest_test(
                ar,
                valid_user_header,
                path,
                "http://127.0.0.3:{}".format(dest_port),
                )

    def test_if_mesos_leader_is_reresolved_by_lua(
            self, nginx_class, mocker, dns_server_mock, valid_user_header):
        # Change the TTL of `leader.mesos.` entry
        dns_server_mock.set_dns_entry(
            'leader.mesos.', ip='127.0.0.2', ttl=self.LONG_TTL)

        # This should be equal or greater than 1.5 times the value of `valid=`
        # DNS TTL override in `resolver` config option -> 5s * 1.5 = 7.5s
        cache_poll_period = 8
        cache_expiration = cache_poll_period - 1
        cache_first_poll = 1

        # We can just ask Mesos endpoints to perform request recording here,
        # but varying the responses of the Mesos endpoints will make tests less
        # prone to timing issues (i.e. `first poll` cache request will result
        # both mocks recording requests).
        mocker.send_command(
            endpoint_id='http://127.0.0.3:5050',
            func_name='enable_extra_agent',
            )

        ar = nginx_class(
            cache_first_poll_delay=cache_first_poll,
            cache_poll_period=cache_poll_period,
            cache_expiration=cache_expiration,
            upstream_mesos="http://leader.mesos:5050",
            )

        with GuardedSubprocess(ar):
            # Force cache update by issuing a request
            ping_mesos_agent(
                ar,
                valid_user_header,
                expect_status=404,
                agent_id=AGENT_EXTRA_ID)

            # Now, let's change DNS entry to point to other Mesos master
            dns_server_mock.set_dns_entry(
                'leader.mesos.', ip='127.0.0.3', ttl=self.LONG_TTL)

            # Wait for cache to expire and let DNS entry be re-resolved
            # during the refresh
            time.sleep(cache_poll_period + cache_first_poll + 1)

            # Make sure that cache now used the right upstream
            ping_mesos_agent(
                ar,
                valid_user_header,
                expect_status=200,
                endpoint_id='http://127.0.0.4:15003',
                agent_id=AGENT_EXTRA_ID)
