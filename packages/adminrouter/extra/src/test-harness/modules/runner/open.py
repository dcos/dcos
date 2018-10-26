# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""
Module for managing test Open AR instances, against which all tests are run.
"""

import logging
import os

from runner.common import NginxBase

log = logging.getLogger(__name__)


class Nginx(NginxBase):
    """This class represents AR behaviour/configuration specific to Open flavour"""

    def __init__(self,
                 ouath_client_id="3yF5TOSzdlI45Q1xspxzeoGBe9fNxm9m",
                 ouath_auth_redirector="https://auth.dcos.io",
                 auth_token_verification_key_file_path=os.environ.get(
                     "IAM_PUBKEY_FILE_PATH"),
                 **base_kwargs):
        """Initialize new AR/Nginx instance

        Args:
             ouath_client_id (str): translates to `OUATH_CLIENT_ID` env var
             ouath_auth_redirector (str): translates to `OUATH_AUTH_REDIRECTOR`
                env var
             auth_token_verification_key_file_path (str): translates to
                `AUTH_TOKEN_VERIFICATION_KEY_FILE_PATH` env var
        """
        NginxBase.__init__(self, **base_kwargs)

        self._set_ar_env_from_val("OAUTH_CLIENT_ID", ouath_client_id)
        self._set_ar_env_from_val("OAUTH_AUTH_REDIRECTOR", ouath_auth_redirector)
        self._set_ar_env_from_val(
            'AUTH_TOKEN_VERIFICATION_KEY_FILE_PATH',
            auth_token_verification_key_file_path
        )
