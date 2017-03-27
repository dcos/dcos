# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

from generic_test_code.common import assert_endpoint_response
from util import SearchCriteria

EXHIBITOR_PATH = "/exhibitor/foo/bar"


class TestAuthzIAMBackendQuery:
    def test_if_iam_broken_resp_code_is_handled(
            self,
            master_ar_process,
            valid_user_header,
            mocker,
            ):
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8101',
            func_name='always_bork',
            aux_data=True,
            )

        log_messages = {
            'UID from valid JWT: `bozydar`': SearchCriteria(1, True),
            "Unexpected response from IAM: ":
                SearchCriteria(1, True),
            }
        assert_endpoint_response(
            master_ar_process,
            EXHIBITOR_PATH,
            500,
            assert_stderr=log_messages,
            headers=valid_user_header,
            )


class TestAuthnJWTValidatorOpen:
    def test_forged_auth_token(
            self,
            master_ar_process,
            forged_user_header,
            ):
        # Different validators emit different log messages, so we create two
        # tests - one for open, one for EE, each one having different log
        # message.
        log_messages = {
            "Invalid token. Reason: signature mismatch":
                SearchCriteria(1, True),
            }

        assert_endpoint_response(
            master_ar_process,
            EXHIBITOR_PATH,
            401,
            assert_stderr=log_messages,
            headers=forged_user_header,
            )
