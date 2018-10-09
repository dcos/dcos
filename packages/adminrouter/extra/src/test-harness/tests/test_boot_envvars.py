# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import logging
import time

import pytest
import requests

from mocker.endpoints.mesos import AGENT1_ID, AGENT3_ID
from util import GuardedSubprocess, LineBufferFilter, SearchCriteria

log = logging.getLogger(__name__)


@pytest.fixture()
def empty_file(tmp_file):
    open(tmp_file, 'w').close()

    return tmp_file


class TestSecretKeyFilePathEnvVarBehaviour:
    @pytest.mark.parametrize('role', ['master', 'agent'])
    def test_if_not_defining_the_var_is_handled(self, nginx_class, role):
        # Scanning for the exact log entry is bad, but in this case - can't be
        # avoided.
        filter_regexp = {
            'AUTH_TOKEN_VERIFICATION_KEY_FILE_PATH not set.':
                SearchCriteria(1, False)
        }
        ar = nginx_class(role=role, auth_token_verification_key_file_path=None)

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)
            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    @pytest.mark.parametrize('role', ['master', 'agent'])
    def test_if_var_pointing_to_empty_file_is_handled(
            self, nginx_class, role, empty_file):
        # Scanning for the exact log entry is bad, but in this case - can't be
        # avoided.
        filter_regexp = {'Auth token verification key not set': SearchCriteria(1, False)}
        ar = nginx_class(role=role, auth_token_verification_key_file_path=empty_file)

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    # TODO: ATM in Agent-Open there are no paths we can test auth with
    @pytest.mark.parametrize('role,use_empty',
                             [('master', False), ('master', True)],
                             )
    def test_if_bad_var_fails_all_requests(
            self, nginx_class, role, use_empty, empty_file, valid_user_header):

        if use_empty:
            ar = nginx_class(role=role, auth_token_verification_key_file_path=empty_file)
        else:
            ar = nginx_class(role=role, auth_token_verification_key_file_path=None)
        url = ar.make_url_from_path()

        with GuardedSubprocess(ar):
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)

        assert resp.status_code == 401


class TestDefaultSchemeEnvVarBehaviour:
    def test_if_default_scheme_is_honoured_by_agent_endpoint(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {'Default scheme: https://': SearchCriteria(1, False)}

        ar = nginx_class(default_scheme="https://")
        agent_id = AGENT3_ID
        url_good = ar.make_url_from_path('/agent/{}/blah/blah'.format(agent_id))
        agent_id = AGENT1_ID
        url_bad = ar.make_url_from_path('/agent/{}/blah/blah'.format(agent_id))

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)

            resp = requests.get(url_bad,
                                allow_redirects=False,
                                headers=valid_user_header)

            assert resp.status_code == 502

            resp = requests.get(url_good,
                                allow_redirects=False,
                                headers=valid_user_header)

            assert resp.status_code == 200
            req_data = resp.json()
            assert req_data['endpoint_id'] == 'https://127.0.0.1:15401'

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    def test_if_default_scheme_is_honourded_by_mleader_endpoint(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {'Default scheme: https://': SearchCriteria(1, False)}

        cache_poll_period = 3
        ar = nginx_class(cache_poll_period=cache_poll_period,
                         cache_expiration=cache_poll_period - 1,
                         default_scheme="https://")
        url = ar.make_url_from_path('/system/v1/leader/marathon/foo/bar/baz')

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)

            assert resp.status_code == 502

            mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                func_name='change_leader',
                                aux_data="127.0.0.4:443")

            # First poll (2s) + normal poll interval(4s) < 2 * normal poll
            # interval(4s)
            time.sleep(cache_poll_period * 2)

            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)

            assert resp.status_code == 200
            req_data = resp.json()
            assert req_data['endpoint_id'] == 'https://127.0.0.4:443'

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}


class TestUpstreamsEnvVarBehaviour:
    def test_if_marathon_upstream_env_is_honoured(
            self, nginx_class, mocker, valid_user_header):

        # Stage 0 - setup the environment:
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='record_requests')

        mocker.send_command(endpoint_id='http://127.0.0.2:8080',
                            func_name='record_requests')

        # Stage 1 - we set Marathon upstream to http://127.0.0.1:8080 and
        # verify that all the requests from cache go there:
        filter_regexp = {
            'Marathon upstream: http://127.0.0.1:8080': SearchCriteria(1, True),
            'Request url: http://127.0.0.1:8080/v2/leader': SearchCriteria(1, True),
            ('Request url: http://127.0.0.1:8080/v2/apps'
             '\?embed=apps\.tasks\&label=DCOS_SERVICE_NAME'): SearchCriteria(1, True),
        }

        ar = nginx_class(upstream_marathon="http://127.0.0.1:8080")
        url = ar.make_url_from_path('/system/v1/leader/marathon/foo/bar/baz')

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)
            requests.get(url,
                         allow_redirects=False,
                         headers=valid_user_header)

            lbf.scan_log_buffer()

        m1_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                          func_name='get_recorded_requests')
        assert len(m1_requests) == 2
        m2_requests = mocker.send_command(endpoint_id='http://127.0.0.2:8080',
                                          func_name='get_recorded_requests')
        assert len(m2_requests) == 0

        assert lbf.extra_matches == {}

        # Stage 1 ends

        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='erase_recorded_requests')

        # Stage 2 - we set Marathon upstream to http://127.0.0.2:8080 and
        # verify that all the requests go to the new upstream
        filter_regexp = {
            'Marathon upstream: http://127.0.0.2:8080': SearchCriteria(1, True),
            'Request url: http://127.0.0.2:8080/v2/leader': SearchCriteria(1, True),
            ('Request url: http://127.0.0.2:8080/v2/apps'
             '\?embed=apps\.tasks\&label=DCOS_SERVICE_NAME'): SearchCriteria(1, True),
        }
        ar = nginx_class(upstream_marathon="http://127.0.0.2:8080")

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)
            requests.get(url,
                         allow_redirects=False,
                         headers=valid_user_header)

            lbf.scan_log_buffer()

        m1_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                          func_name='get_recorded_requests')
        assert len(m1_requests) == 0
        m2_requests = mocker.send_command(endpoint_id='http://127.0.0.2:8080',
                                          func_name='get_recorded_requests')
        assert len(m2_requests) == 2

        assert lbf.extra_matches == {}

    def test_if_mesos_upstream_env_is_honoured(
            self, nginx_class, mocker, valid_user_header):

        # Stage 0 - setup the environment:
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')

        mocker.send_command(endpoint_id='http://127.0.0.3:5050',
                            func_name='record_requests')

        # Stage 1 - we set Mesos upstream to http://127.0.0.2:5050 and
        # verify that all the requests from cache go there:
        filter_regexp = {
            'Mesos upstream: http://127.0.0.2:5050': SearchCriteria(1, True),
            'Request url: http://127.0.0.2:5050/master/state-summary': SearchCriteria(1, True),
        }

        ar = nginx_class(upstream_mesos="http://127.0.0.2:5050")
        agent_id = AGENT1_ID
        url = ar.make_url_from_path('/agent/{}/blah/blah'.format(agent_id))

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)
            requests.get(url,
                         allow_redirects=False,
                         headers=valid_user_header)

            lbf.scan_log_buffer()

        m1_requests = mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                          func_name='get_recorded_requests')
        assert len(m1_requests) == 1
        m2_requests = mocker.send_command(endpoint_id='http://127.0.0.3:5050',
                                          func_name='get_recorded_requests')
        assert len(m2_requests) == 0

        assert lbf.extra_matches == {}

        # Stage 1 ends

        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='erase_recorded_requests')

        # Stage 2 - we set Mesos upstream to http://127.0.0.2:8080 and
        # verify that all the requests go to the new upstream
        filter_regexp = {
            'Mesos upstream: http://127.0.0.3:5050': SearchCriteria(1, True),
            'Request url: http://127.0.0.3:5050/master/state-summary': SearchCriteria(1, True),
        }
        ar = nginx_class(upstream_mesos="http://127.0.0.3:5050")

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)
            requests.get(url,
                         allow_redirects=False,
                         headers=valid_user_header)

            lbf.scan_log_buffer()

        m1_requests = mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                          func_name='get_recorded_requests')
        assert len(m1_requests) == 0
        m2_requests = mocker.send_command(endpoint_id='http://127.0.0.3:5050',
                                          func_name='get_recorded_requests')
        assert len(m2_requests) == 1

        assert lbf.extra_matches == {}


class TestHostIPVarBehavriour:
    def test_if_absent_var_is_handled(self, nginx_class, mocker):
        filter_regexp = {
            'Local Mesos Master IP: unknown': SearchCriteria(1, True),
        }
        ar = nginx_class(host_ip=None)

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    @pytest.mark.parametrize(
        "invalid_ip",
        ["not-an-ip", "1,3,4,4", "1.2.3.300", 'aaa.1.2.3.4', '1.2.3.4.bccd'])
    def test_if_var_is_verified(self, invalid_ip, nginx_class, mocker):
        filter_regexp = {
            'Local Mesos Master IP: unknown': SearchCriteria(1, True),
            'HOST_IP var is not a valid ipv4: {}'.format(invalid_ip):
                SearchCriteria(1, True),
        }
        ar = nginx_class(host_ip=invalid_ip)

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    @pytest.mark.parametrize("valid_ip", ["1.2.3.4", "255.255.255.255", "0.0.0.1"])
    def test_if_var_is_honoured(self, valid_ip, nginx_class, mocker):
        filter_regexp = {
            'Local Mesos Master IP: {}'.format(valid_ip): SearchCriteria(1, True),
        }
        ar = nginx_class(host_ip=valid_ip)

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)

            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}


class TestAuthModuleDisablingMaster:
    @pytest.mark.parametrize(
        "enable_keyword",
        ["enabled", "true", "yes", "of_course", "make it so!",
         "disabled", "no", "no way", "please no"])
    def test_if_auth_module_is_enabled_by_unless_false_str_is_provided(
            self, nginx_class, mocker, enable_keyword):
        filter_regexp = {
            'Activate authentication module.': SearchCriteria(1, True),
        }
        ar = nginx_class(auth_enabled=enable_keyword)
        url = ar.make_url_from_path('/exhibitor/foo/bar')

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)

            resp = requests.get(url,
                                allow_redirects=False)

            assert resp.status_code == 401
            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    def test_if_auth_module_can_be_disabled(self, nginx_class, mocker):
        filter_regexp = {
            ("ADMINROUTER_ACTIVATE_AUTH_MODULE set to `false`. "
             "Deactivate authentication module."): SearchCriteria(1, True),
        }
        ar = nginx_class(auth_enabled='false')
        url = ar.make_url_from_path('/exhibitor/foo/bar')

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)

            resp = requests.get(url,
                                allow_redirects=False)

            assert resp.status_code == 200
            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}
