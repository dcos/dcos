# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import logging
import pytest
import requests

from util import LineBufferFilter

log = logging.getLogger(__name__)


@pytest.fixture()
def empty_file(tmp_file):
    open(tmp_file, 'w').close()

    return tmp_file


@pytest.fixture(scope='function')
def ar_process_without_secret_key(nginx_class, request, empty_file):
    """Provide a (master|agent) AR process which has `SECRET_KEY_FILE_PATH`
       variable (empty|not-set), depending on the parameters passed to the
       fixture."""
    role = request.param[0]
    use_empty = request.param[1]

    if use_empty:
        nginx = nginx_class(role=role, secret_key_file_path=empty_file)
    else:
        nginx = nginx_class(role=role, secret_key_file_path=None)

    nginx.start()

    yield nginx

    nginx.stop()


class TestSecretKeyFilePathEnvVarBehaviour():
    @pytest.mark.parametrize('ar_process_without_secret_key',
                             [('master', False), ('agent', False)],
                             indirect=['ar_process_without_secret_key'],
                             )
    def test_if_not_defining_the_var_is_handled(self,
                                                ar_process_without_secret_key):
        # Scanning for the exact log entry is bad, but in this case - can't be
        # avoided.
        filter_regexp = 'SECRET_KEY_FILE_PATH not set.'

        lbf = LineBufferFilter(filter_regexp,
                               line_buffer=ar_process_without_secret_key.stderr_line_buffer)

        lbf.scan_log_buffer()

        assert lbf.all_found is True

    @pytest.mark.parametrize('ar_process_without_secret_key',
                             [('master', True), ('agent', True)],
                             indirect=['ar_process_without_secret_key'],
                             )
    def test_if_var_pointing_to_empty_file_is_handled(self,
                                                      ar_process_without_secret_key):
        # Scanning for the exact log entry is bad, but in this case - can't be
        # avoided.
        filter_regexp = 'Secret key not set or empty string.'

        lbf = LineBufferFilter(filter_regexp,
                               line_buffer=ar_process_without_secret_key.stderr_line_buffer)

        lbf.scan_log_buffer()

        assert lbf.all_found is True

    # TODO: ATM in Agent-Open there are no paths we can test auth with
    @pytest.mark.parametrize('ar_process_without_secret_key',
                             [('master', False), ('master', True)],
                             indirect=['ar_process_without_secret_key'],
                             )
    def test_if_bad_var_fails_all_requests(self,
                                           ar_process_without_secret_key,
                                           valid_user_header):

        url = ar_process_without_secret_key.make_url_from_path()
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 401
