import getpass
import logging
import os
import pwd
import random
import string
import subprocess

from kazoo.client import KazooClient, KazooRetry

from dcos_internal_utils import bootstrap

logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class TestBootstrap():
    def setup_class(self):
        self.tmpdir = os.path.abspath('tmp')
        os.makedirs(self.tmpdir, exist_ok=True)

        self.zk_container_name = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        subprocess.check_call(['sudo', 'docker', 'run', '-d', '-p', '2181:2181', '-p',
                               '2888:2888', '-p', '3888:3888', '--name', self.zk_container_name, 'jplock/zookeeper'])
        self.zk_hosts = '127.0.0.1:2181'

        conn_retry_policy = KazooRetry(max_tries=-1, delay=0.1, max_delay=0.1)
        cmd_retry_policy = KazooRetry(max_tries=3, delay=0.3, backoff=1, max_delay=1, ignore_expire=False)
        zk = KazooClient(hosts=self.zk_hosts, connection_retry=conn_retry_policy, command_retry=cmd_retry_policy)
        zk.start()

        children = zk.get_children('/')
        for child in children:
            if child == 'zookeeper':
                continue
            zk.delete('/' + child, recursive=True)

        self.zk = zk

    def teardown_class(self):
        self.zk.stop()
        self.zk.close()
        subprocess.check_call(['sudo', 'docker', 'rm', '-f', self.zk_container_name])

    def _test_consensus(self, methodname, monkeypatch):
        orig_getpwnam = pwd.getpwnam

        def mock_getpwnam(user):
            return orig_getpwnam(getpass.getuser())
        monkeypatch.setattr(pwd, 'getpwnam', mock_getpwnam)

        b = bootstrap.Bootstrapper(self.zk_hosts)

        path = self.tmpdir + '/cluster-id'

        try:
            os.remove(path)
        except FileNotFoundError:
            pass

        method = getattr(b, methodname)

        id1 = method(path)
        os.remove(path)
        id2 = method(path)
        assert id1 == id2

    def test_bootstrap(self, monkeypatch):
        self._test_consensus('cluster_id', monkeypatch)

    def test_generate_oauth_secret(self, monkeypatch):
        self._test_consensus('generate_oauth_secret', monkeypatch)
