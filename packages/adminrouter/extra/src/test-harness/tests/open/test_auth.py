# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import pytest
import requests

from generic_test_code.common import (
    assert_endpoint_response,
    overridden_file_content,
)
from util import GuardedSubprocess, SearchCriteria

EXHIBITOR_PATH = "/exhibitor/foo/bar"

# Note(JP): this test seems to rely on the assumption that the IAM is in the hot
# path for "authorization". By design, this should not be the case.

# class TestAuthzIAMBackendQuery:
#     def test_if_iam_broken_resp_code_is_handled(
#             self,
#             master_ar_process_perclass,
#             valid_user_header,
#             mocker,
#             ):
#         mocker.send_command(
#             endpoint_id='http://127.0.0.1:8101',
#             func_name='always_bork',
#             aux_data=True,
#             )

#         log_messages = {
#             'UID from the valid DC/OS authentication token: `bozydar`':
#                 SearchCriteria(1, True),
#             "Unexpected response from IAM: ":
#                 SearchCriteria(1, True),
#             }
#         assert_endpoint_response(
#             master_ar_process_perclass,
#             EXHIBITOR_PATH,
#             500,
#             assert_stderr=log_messages,
#             headers=valid_user_header,
#             )


class TestAuthnJWTValidatorOpen:
    def test_forged_auth_token(
            self,
            master_ar_process_perclass,
            forged_user_header,
            ):
        # Different validators emit different log messages, so we create two
        # tests - one for open, one for EE, each one having different log
        # message.
        log_messages = {
            "Invalid token":
                SearchCriteria(1, True),
            }

        assert_endpoint_response(
            master_ar_process_perclass,
            EXHIBITOR_PATH,
            401,
            assert_stderr=log_messages,
            headers=forged_user_header,
            )


class TestOauthLoginIntegration:
    @pytest.mark.parametrize(
        "oa_redir,oa_client_id,oa_cluster_id",
        (["https://auth.dcos.io",
          "GiVuhyheiccetcyudJooshac492341sd",
          "fd615e91-2316-43e2-9f64-390c9256203f",
          ],
         ["https://test.abc.ef",
          "dsaftq13435gssgfw342t2gwr4326uuw",
          "bcde3e6d-a6dc-4269-abb7-252910e942f7",
          ],
         )
        )
    def test_if_login_url_works(
            self,
            nginx_class,
            oa_redir,
            oa_client_id,
            oa_cluster_id,
            ):
        ar = nginx_class(
            ouath_client_id=oa_client_id,
            ouath_auth_redirector=oa_redir)
        url = ar.make_url_from_path('/login?a=1&b=2')
        expected_path = "{}/login?client={}&cluster_id={}&a=1&b=2".format(
            oa_redir, oa_client_id, oa_cluster_id)

        with overridden_file_content('/var/lib/dcos/cluster-id', oa_cluster_id):
            with GuardedSubprocess(ar):
                r = requests.get(url, allow_redirects=False)

        assert r.status_code == 302
        assert r.headers['Location'] == expected_path
