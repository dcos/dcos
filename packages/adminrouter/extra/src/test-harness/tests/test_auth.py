# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import os
import time

import pytest
import requests

from generic_test_code.common import assert_endpoint_response
from util import GuardedSubprocess, SearchCriteria, auth_type_str

EXHIBITOR_PATH = "/exhibitor/foo/bar"


# Note(JP): this test assumes that the IAM is contacted when trying to reach
# /mesos_dns. This is not a good assumption. TODO: rewrite the test so that
# setting the User-Agent header is somehow tested differently.

# class TestAuthzIAMBackendQueryCommon:


#     def test_if_master_ar_sets_correct_useragent_while_quering_iam(
#             self, master_ar_process_pertest, mocker, valid_user_header):
#         mocker.send_command(endpoint_id='http://127.0.0.1:8101',
#                             func_name='record_requests')

#         assert_endpoint_response(
#             master_ar_process_pertest,
#             '/mesos_dns/v1/reflect/me',
#             200,
#             headers=valid_user_header,
#             )

#         r_reqs = mocker.send_command(endpoint_id='http://127.0.0.1:8101',
#                                      func_name='get_recorded_requests')

#         assert len(r_reqs) == 1
#         verify_header(r_reqs[0]['headers'], 'User-Agent', 'Master Admin Router')


class TestAuthnJWTValidator:
    """Tests scenarios where authentication token isn't provided or is provided
    in different supported places (cookie, header)"""

    def test_auth_token_not_provided(self, master_ar_process_perclass):
        log_messages = {
            "No auth token in request.": SearchCriteria(1, True),
            }

        assert_endpoint_response(
            master_ar_process_perclass, EXHIBITOR_PATH, 401, assert_stderr=log_messages)

    def test_invalid_auth_token_in_cookie(self, master_ar_process_perclass):
        log_messages = {
            "No auth token in request.": SearchCriteria(0, True),
            "Invalid token. Reason: invalid jwt string":
                SearchCriteria(1, True),
            }

        assert_endpoint_response(
            master_ar_process_perclass,
            EXHIBITOR_PATH,
            401,
            assert_stderr=log_messages,
            cookies={"dcos-acs-auth-cookie": "invalid"},
            )

    # Note(JP): in the future we should simply test that only RS256 works, in
    # both variants.
    # def test_missmatched_auth_token_algo_in_cookie(
    #         self,
    #         master_ar_process_perclass,
    #         mismatch_alg_jwt_generator,
    #         repo_is_ee,
    #         ):
    #     log_messages = {
    #         ("Invalid token. Reason: whitelist unsupported alg: " +
    #          jwt_type_str(not repo_is_ee)): SearchCriteria(1, True),
    #         }

    #     token = mismatch_alg_jwt_generator(uid='user')
    #     assert_endpoint_response(
    #         master_ar_process_perclass,
    #         EXHIBITOR_PATH,
    #         401,
    #         assert_stderr=log_messages,
    #         cookies={"dcos-acs-auth-cookie": token},
    #         )

    def test_valid_auth_token_in_cookie_with_null_uid(
            self,
            master_ar_process_perclass,
            jwt_generator,
            ):
        log_messages = {
            "No auth token in request.": SearchCriteria(0, True),
            "Invalid token. Reason: invalid jwt string":
                SearchCriteria(0, True),
            "Unexpected token payload: missing uid.":
                SearchCriteria(1, True),
            }

        token = jwt_generator(uid=None)
        assert_endpoint_response(
            master_ar_process_perclass,
            EXHIBITOR_PATH,
            401,
            assert_stderr=log_messages,
            cookies={"dcos-acs-auth-cookie": token},
            )

    def test_valid_auth_token_in_cookie(
            self,
            master_ar_process_perclass,
            jwt_generator):
        log_messages = {
            "No auth token in request.": SearchCriteria(0, True),
            "Invalid token. Reason: invalid jwt string":
                SearchCriteria(0, True),
            "UID from the valid DC/OS authentication token: `test`": SearchCriteria(1, True),
            }

        token = jwt_generator(uid='test')
        assert_endpoint_response(
            master_ar_process_perclass,
            EXHIBITOR_PATH,
            200,
            assert_stderr=log_messages,
            cookies={"dcos-acs-auth-cookie": token},
            )

    def test_valid_auth_token(self, master_ar_process_perclass, valid_user_header):
        log_messages = {
            "UID from the valid DC/OS authentication token: `bozydar`":
                SearchCriteria(1, True),
            }
        assert_endpoint_response(
            master_ar_process_perclass,
            EXHIBITOR_PATH,
            200,
            assert_stderr=log_messages,
            headers=valid_user_header,
            )

    def test_valid_auth_token_priority(
            self,
            master_ar_process_perclass,
            valid_user_header,
            jwt_generator,
            ):
        log_messages = {
            "UID from the valid DC/OS authentication token: `bozydar`":
                SearchCriteria(1, True),
            "UID from the valid DC/OS authentication token: `test`":
                SearchCriteria(0, True),
            }

        token = jwt_generator(uid='test')
        assert_endpoint_response(
            master_ar_process_perclass,
            EXHIBITOR_PATH,
            200,
            assert_stderr=log_messages,
            headers=valid_user_header,
            cookies={"dcos-acs-auth-cookie": token},
            )

    def test_valid_auth_token_without_uid(
            self,
            master_ar_process_perclass,
            jwt_generator,
            ):
        log_messages = {
            "Invalid token. Reason: Missing one of claims - \[ uid \]":
                SearchCriteria(1, True),
            }

        token = jwt_generator(uid='test', skip_uid_claim=True)
        auth_header = {'Authorization': 'token={}'.format(token)}
        assert_endpoint_response(
            master_ar_process_perclass,
            EXHIBITOR_PATH,
            401,
            assert_stderr=log_messages,
            headers=auth_header,
            )

    def test_valid_auth_token_without_exp(
            self,
            master_ar_process_perclass,
            jwt_generator,
            ):
        # We accept "forever tokens"
        token = jwt_generator(uid='test', skip_exp_claim=True)
        auth_header = {'Authorization': 'token={}'.format(token)}
        assert_endpoint_response(
            master_ar_process_perclass,
            EXHIBITOR_PATH,
            200,
            headers=auth_header,
            )

    def test_expired_auth_token(
            self,
            master_ar_process_perclass,
            jwt_generator,
            ):
        log_messages = {
            "Invalid token. Reason: 'exp' claim expired at ":
                SearchCriteria(1, True),
            }

        token = jwt_generator(uid='test', exp=time.time() - 15)
        auth_header = {'Authorization': 'token={}'.format(token)}
        assert_endpoint_response(
            master_ar_process_perclass,
            EXHIBITOR_PATH,
            401,
            assert_stderr=log_messages,
            headers=auth_header,
            )

    def test_valid_auth_token_with_bearer_header(
            self,
            master_ar_process_perclass,
            jwt_generator,
            ):
        # We accept "forever tokens"
        token = jwt_generator(uid='test')
        auth_header = {'Authorization': 'Bearer {}'.format(token)}
        assert_endpoint_response(
            master_ar_process_perclass,
            EXHIBITOR_PATH,
            200,
            headers=auth_header,
            )


class TestAuthCustomErrorPages:
    def test_correct_401_page_content(self, master_ar_process_pertest, repo_is_ee):
        url = master_ar_process_pertest.make_url_from_path(EXHIBITOR_PATH)
        resp = requests.get(url)

        assert resp.status_code == 401
        assert resp.headers["Content-Type"] == "text/html; charset=UTF-8"
        assert resp.headers["WWW-Authenticate"] == auth_type_str(repo_is_ee)

        path_401 = os.environ.get('AUTH_ERROR_PAGE_DIR_PATH') + "/401.html"
        with open(path_401, 'rb') as f:
            resp_content = resp.content.decode('utf-8').strip()
            file_content = f.read().decode('utf-8').strip()
            assert resp_content == file_content


class TestAuthPrecedence:
    def test_if_service_endpoint_auth_precedence_is_enforced(
            self,
            valid_user_header,
            master_ar_process_pertest):

        url = master_ar_process_pertest.make_url_from_path("/service/i/do/not/exist")
        resp = requests.get(
            url,
            allow_redirects=False)

        assert resp.status_code == 401

        resp = requests.get(
            url,
            allow_redirects=False,
            headers=valid_user_header)

        assert resp.status_code == 404

    @pytest.mark.parametrize("path", ["/system/v1/agent/{}/logs{}", "/agent/{}{}"])
    def test_if_agent_endpoint_auth_precedence_is_enforced(
            self,
            valid_user_header,
            master_ar_process_pertest,
            path):

        uri = path.format("bdcd424a-b59e-4df4-b492-b54e38926bd8-S0", "/foo/bar")
        url = master_ar_process_pertest.make_url_from_path(uri)
        resp = requests.get(
            url,
            allow_redirects=False)

        assert resp.status_code == 401

        resp = requests.get(
            url,
            allow_redirects=False,
            headers=valid_user_header)

        assert resp.status_code == 404

    def test_if_mleader_endpoint_auth_precedence_is_enforced(
            self,
            valid_user_header,
            master_ar_process_pertest,
            mocker):

        # We have to remove the leader in order to make AR respond with 404
        # which has a chance of being processed earlier than auth.
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='remove_leader')
        url = master_ar_process_pertest.make_url_from_path(
            "/system/v1/leader/marathon/foo/bar")
        resp = requests.get(
            url,
            allow_redirects=False)

        assert resp.status_code == 401

        resp = requests.get(
            url,
            allow_redirects=False,
            headers=valid_user_header)

        assert resp.status_code == 503

    def test_if_historyservice_endpoint_auth_precedence_is_enforced(
            self, valid_user_header, mocker, nginx_class):

        ar = nginx_class(host_ip=None)
        url = ar.make_url_from_path('/dcos-history-service/foo/bar')

        with GuardedSubprocess(ar):
            resp = requests.get(url, allow_redirects=False)
            assert resp.status_code == 401

            resp = requests.get(url, allow_redirects=False, headers=valid_user_header)
            assert resp.status_code == 503
