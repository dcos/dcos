import grp
import os

import psutil
import pytest
import requests
import textwrap

import generic_test_code.common
from generic_test_code.common import (
    header_is_absent,
    overridden_file_content,
    verify_header,
)
from util import GuardedSubprocess, auth_type_str, iam_denies_all_requests

EXHIBITOR_PATH = "/exhibitor/foo/bar"


# A hack to be able to parameterize a test with multiple fixtures.
# https://github.com/pytest-dev/pytest/issues/349#issuecomment-189370273
@pytest.fixture(
    params=[
        'agent_ar_process_pertest',
        'master_ar_process_pertest'
    ])
def ar_process(request):
    return request.getfixturevalue(request.param)


class TestNginxWorkersGroup:
    def test_if_nginx_workers_on_master_have_correct_group(
            self, ar_process):
        gid = grp.getgrnam('dcos_adminrouter').gr_gid
        for proc in psutil.process_iter():
            if proc.pid == ar_process.pid:
                if proc.children():
                    for child in proc.children():
                        effective_gid = child.gids()[1]
                        assert gid == effective_gid, "Process not running as dcos_adminrouter"


class TestCustomErrorPages:
    def test_correct_401_page_content(self, master_ar_process_pertest, repo_is_ee):
        url = master_ar_process_pertest.make_url_from_path(EXHIBITOR_PATH)
        resp = requests.get(url)

        assert resp.status_code == 401
        verify_header(resp.headers.items(), 'Content-Type', "text/html; charset=UTF-8")
        verify_header(resp.headers.items(), 'WWW-Authenticate', auth_type_str(repo_is_ee))
        verify_header(resp.headers.items(), 'Server', "openresty")

        path_401 = os.environ.get('AUTH_ERROR_PAGE_DIR_PATH') + "/401.html"
        with open(path_401, 'rb') as f:
            resp_content = resp.content.decode('utf-8').strip()
            file_content = f.read().decode('utf-8').strip()
            assert resp_content == file_content

    @pytest.mark.skipif(
        not generic_test_code.common.repo_is_ee(),
        reason="403 can only be tested in EE" +
               "as Open DC/OS IAM has no notion of being `unauthorized`, only " +
               "unauthenticated.")
    def test_correct_403_page_content(
            self, master_ar_process_pertest, valid_user_header, mocker):
        url = master_ar_process_pertest.make_url_from_path(EXHIBITOR_PATH)

        with iam_denies_all_requests(mocker):
            resp = requests.get(url, headers=valid_user_header)

        assert resp.status_code == 403
        verify_header(resp.headers.items(), 'Content-Type', "text/html; charset=UTF-8")
        verify_header(resp.headers.items(), 'Server', "openresty")
        header_is_absent(resp.headers.items(), 'WWW-Authenticate')

        path_403 = os.environ.get('AUTH_ERROR_PAGE_DIR_PATH') + "/403.html"
        with open(path_403, 'rb') as f:
            resp_content = resp.content.decode('utf-8').strip()
            file_content = f.read().decode('utf-8').strip()
            assert resp_content == file_content

    # This test has not been generalized into test_correct_5xx_page_content
    # test as we have a reliable way to force a 404 reply from the AR. Hence we
    # are a bit more accurate here and perform 404 test without artificially
    # modifying the AR configuration. The trade-off of slightly more copy-paste
    # code seems to be acceptable.
    def test_correct_404_page_content(self, ar_process):
        url = ar_process.make_url_from_path('/foo/bar')
        resp = requests.get(url)

        assert resp.status_code == 404
        verify_header(resp.headers.items(), 'Content-Type', "text/html; charset=UTF-8")
        verify_header(resp.headers.items(), 'Server', "openresty")
        header_is_absent(resp.headers.items(), 'WWW-Authenticate')

        path_404 = os.environ.get('AUTH_ERROR_PAGE_DIR_PATH') + "/404.html"
        with open(path_404, 'rb') as f:
            resp_content = resp.content.decode('utf-8').strip()
            file_content = f.read().decode('utf-8').strip()
            assert resp_content == file_content

    @pytest.mark.parametrize("http_code", [500, 501, 502, 503, 504])
    def test_correct_5xx_page_content(self, nginx_class, http_code):
        ar = nginx_class()

        url_path = '/foo/bar/give_me_{}.html'.format(http_code)
        url = ar.make_url_from_path(url_path)

        cur_dir = os.path.dirname(__file__)
        dst_cfg_path = os.path.abspath(
            os.path.join(cur_dir, "..", "..", "includes", "server", "common.conf"))
        with open(dst_cfg_path, 'r') as fh:
            test_root_cfg = fh.read()
            fmt = textwrap.dedent("""
                location ~ "^/foo/bar/give_me_{resp_code}.html" {{
                    return {resp_code};
                }}
                """)
            for i in [500, 501, 502, 503, 504]:
                test_root_cfg += fmt.format(resp_code=i)

        # This is a hack to make remaining 5xx codes testable - we are
        # temporarily substituting one of Nginx's config files with the file
        # that is suitable for our testing needs. The changes in configuration
        # are scoped to only this small code block and are unrelated to error
        # pages code handling itself.
        # Due to the nature of Admin Router tests (i.e. a black-box testing),
        # this seems like an acceptable approach.
        with overridden_file_content(dst_cfg_path, test_root_cfg):
            with GuardedSubprocess(ar):
                resp = requests.get(url)

        assert resp.status_code == http_code
        verify_header(resp.headers.items(), 'Content-Type', "text/html; charset=UTF-8")
        verify_header(resp.headers.items(), 'Server', "openresty")
        header_is_absent(resp.headers.items(), 'WWW-Authenticate')

        err_page_path = "{}/{}.html".format(
            os.environ.get('AUTH_ERROR_PAGE_DIR_PATH'),
            http_code)
        with open(err_page_path, 'rb') as f:
            resp_content = resp.content.decode('utf-8').strip()
            file_content = f.read().decode('utf-8').strip()
            assert resp_content == file_content
