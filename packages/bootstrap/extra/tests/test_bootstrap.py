import getpass
import logging
try:
    import pwd
except ImportError:
    pass
import random
import string
import subprocess
import sys

import pytest
from kazoo.client import KazooClient, KazooRetry

from dcos_internal_utils import bootstrap
from pkgpanda.util import is_windows

if not is_windows:
    assert 'pwd' in sys.modules

zookeeper_docker_image = 'jplock/zookeeper'
zookeeper_docker_run_args = ['--publish=2181:2181', '--publish=2888:2888', '--publish=3888:3888']

logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

zk_hosts = '127.0.0.1:2181'


@pytest.fixture(scope='function')
def zk_server(tmpdir):
    zk_container_name = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    # TODO(cmaloney): Add a python context manager for dockerized daemons
    subprocess.check_call(
        ['docker', 'run', '-d', '--name', zk_container_name] + zookeeper_docker_run_args + [zookeeper_docker_image]
    )

    conn_retry_policy = KazooRetry(max_tries=-1, delay=0.1, max_delay=0.1)
    cmd_retry_policy = KazooRetry(max_tries=3, delay=0.3, backoff=1, max_delay=1, ignore_expire=False)
    zk = KazooClient(hosts=zk_hosts, connection_retry=conn_retry_policy, command_retry=cmd_retry_policy)
    zk.start()

    children = zk.get_children('/')
    for child in children:
        if child == 'zookeeper':
            continue
        zk.delete('/' + child, recursive=True)

    yield zk

    zk.stop()
    zk.close()
    subprocess.check_call(['docker', 'rm', '-f', zk_container_name])


def _check_consensus(methodname, monkeypatch, tmpdir):
    orig_getpwnam = pwd.getpwnam

    def mock_getpwnam(user):
        return orig_getpwnam(getpass.getuser())
    monkeypatch.setattr(pwd, 'getpwnam', mock_getpwnam)

    b = bootstrap.Bootstrapper(zk_hosts)

    path = tmpdir.join('/cluster-id')
    assert not path.exists()

    method = getattr(b, methodname)

    id1 = method(str(path))
    path.remove()
    id2 = method(str(path))
    assert id1 == id2


@pytest.mark.skipif(is_windows, reason="test fails on Windows reason: docker file does not work on windows")
def test_bootstrap(zk_server, monkeypatch, tmpdir):
    _check_consensus('cluster_id', monkeypatch, tmpdir)


@pytest.mark.skipif(is_windows, reason="test fails on Windows reason: docker file does not work on windows")
def test_generate_oauth_secret(zk_server, monkeypatch, tmpdir):
    _check_consensus('generate_oauth_secret', monkeypatch, tmpdir)
