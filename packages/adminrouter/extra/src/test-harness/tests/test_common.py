import grp

import psutil
import pytest


# A hack to be able to parameterize a test with multiple fixtures.
# https://github.com/pytest-dev/pytest/issues/349#issuecomment-189370273
@pytest.fixture(
    params=[
        'agent_ar_process_pertest',
        'master_ar_process_pertest'
    ])
def ar_process(request):
    return request.getfuncargvalue(request.param)


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
