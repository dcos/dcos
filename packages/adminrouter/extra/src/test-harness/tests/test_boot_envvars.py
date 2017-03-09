# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import logging
import pytest
import requests
import time

from util import LineBufferFilter, SearchCriteria, GuardedSubprocess

log = logging.getLogger(__name__)


@pytest.fixture()
def empty_file(tmp_file):
    open(tmp_file, 'w').close()

    return tmp_file


class TestSecretKeyFilePathEnvVarBehaviour():
    @pytest.mark.parametrize('role', ['master', 'agent'])
    def test_if_not_defining_the_var_is_handled(self, nginx_class, role):
        # Scanning for the exact log entry is bad, but in this case - can't be
        # avoided.
        filter_regexp = 'SECRET_KEY_FILE_PATH not set.'
        ar = nginx_class(role=role, secret_key_file_path=None)

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)
            lbf.scan_log_buffer()

        assert lbf.all_found is True

    @pytest.mark.parametrize('role', ['master', 'agent'])
    def test_if_var_pointing_to_empty_file_is_handled(
            self, nginx_class, role, empty_file):
        # Scanning for the exact log entry is bad, but in this case - can't be
        # avoided.
        filter_regexp = 'Secret key not set or empty string.'
        ar = nginx_class(role=role, secret_key_file_path=empty_file)

        with GuardedSubprocess(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   line_buffer=ar.stderr_line_buffer)

            lbf.scan_log_buffer()

        assert lbf.all_found is True

    # TODO: ATM in Agent-Open there are no paths we can test auth with
    @pytest.mark.parametrize('role,use_empty',
                             [('master', False), ('master', True)],
                             )
    def test_if_bad_var_fails_all_requests(
            self, nginx_class, role, use_empty, empty_file, valid_user_header):

        if use_empty:
            ar = nginx_class(role=role, secret_key_file_path=empty_file)
        else:
            ar = nginx_class(role=role, secret_key_file_path=None)
        url = ar.make_url_from_path()

        with GuardedSubprocess(ar):
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)

        assert resp.status_code == 401
