# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import os
import requests

from generic_test_code.common import (
    assert_endpoint_response,
    )
from util import (
    SearchCriteria,
    auth_type_str,
    jwt_type_str,
)

EXHIBITOR_PATH = "/exhibitor/foo/bar"


class TestAuthnJWTValidator:
    """Tests scenarios where authentication token isn't provided or is provided
    in different supported places (cookie, header)"""

    def test_auth_token_not_provided(self, master_ar_process):
        log_messages = {
            "No auth token in request.": SearchCriteria(1, True),
            }

        assert_endpoint_response(
            master_ar_process, EXHIBITOR_PATH, 401, assert_stderr=log_messages)

    def test_invalid_auth_token_in_cookie(self, master_ar_process):
        log_messages = {
            "No auth token in request.": SearchCriteria(0, True),
            "Invalid token. Reason: invalid jwt string":
                SearchCriteria(1, True),
            }

        assert_endpoint_response(
            master_ar_process,
            EXHIBITOR_PATH,
            401,
            assert_stderr=log_messages,
            cookies={"dcos-acs-auth-cookie": "invalid"},
            )

    def test_missmatched_auth_token_algo_in_cookie(
            self,
            master_ar_process,
            mismatch_alg_jwt_generator,
            repo_is_ee,
            ):
        log_messages = {
            ("Invalid token. Reason: whitelist unsupported alg: " +
             jwt_type_str(not repo_is_ee)): SearchCriteria(1, True),
            }

        token = mismatch_alg_jwt_generator(uid='user')
        assert_endpoint_response(
            master_ar_process,
            EXHIBITOR_PATH,
            401,
            assert_stderr=log_messages,
            cookies={"dcos-acs-auth-cookie": token},
            )

    def test_valid_auth_token_in_cookie_without_uid(
            self,
            master_ar_process,
            valid_jwt_generator,
            ):
        log_messages = {
            "No auth token in request.": SearchCriteria(0, True),
            "Invalid token. Reason: invalid jwt string":
                SearchCriteria(0, True),
            "Unexpected token payload: missing uid.":
                SearchCriteria(1, True),
            }

        token = valid_jwt_generator(uid=None)
        assert_endpoint_response(
            master_ar_process,
            EXHIBITOR_PATH,
            401,
            assert_stderr=log_messages,
            cookies={"dcos-acs-auth-cookie": token},
            )

    def test_valid_auth_token_in_cookie(self, master_ar_process, valid_jwt_generator):
        log_messages = {
            "No auth token in request.": SearchCriteria(0, True),
            "Invalid token. Reason: invalid jwt string":
                SearchCriteria(0, True),
            "UID from valid JWT: `test`": SearchCriteria(1, True),
            }

        token = valid_jwt_generator(uid='test')
        assert_endpoint_response(
            master_ar_process,
            EXHIBITOR_PATH,
            200,
            assert_stderr=log_messages,
            cookies={"dcos-acs-auth-cookie": token},
            )

    def test_valid_auth_token(self, master_ar_process, valid_user_header):
        log_messages = {
            "UID from valid JWT: `bozydar`": SearchCriteria(1, True),
            }
        assert_endpoint_response(
            master_ar_process,
            EXHIBITOR_PATH,
            200,
            assert_stderr=log_messages,
            headers=valid_user_header,
            )

    def test_valid_auth_token_priority(
            self,
            master_ar_process,
            valid_user_header,
            valid_jwt_generator,
            ):
        log_messages = {
            "UID from valid JWT: `bozydar`": SearchCriteria(1, True),
            "UID from valid JWT: `test`": SearchCriteria(0, True),
            }

        token = valid_jwt_generator(uid='test')
        assert_endpoint_response(
            master_ar_process,
            EXHIBITOR_PATH,
            200,
            assert_stderr=log_messages,
            headers=valid_user_header,
            cookies={"dcos-acs-auth-cookie": token},
            )


class TestAuthCustomErrorPages:
    def test_correct_401_page_content(self, master_ar_process, repo_is_ee):
        url = master_ar_process.make_url_from_path(EXHIBITOR_PATH)
        resp = requests.get(url)

        assert resp.status_code == 401
        assert resp.headers["Content-Type"] == "text/html; charset=UTF-8"
        assert resp.headers["WWW-Authenticate"] == auth_type_str(repo_is_ee)

        path_401 = os.environ.get('AUTH_ERROR_PAGE_DIR_PATH') + "/401.html"
        with open(path_401, 'rb') as f:
            resp_content = resp.content.decode('utf-8').strip()
            file_content = f.read().decode('utf-8').strip()
            assert resp_content == file_content
