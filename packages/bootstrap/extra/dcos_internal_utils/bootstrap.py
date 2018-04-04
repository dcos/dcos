import logging
import os
try:
    import pwd
except ImportError:
    pass
import random
import string
import sys
import uuid

import kazoo.exceptions
from kazoo.client import KazooClient
from kazoo.retry import KazooRetry
from kazoo.security import ACL, ANYONE_ID_UNSAFE, Permissions

from dcos_internal_utils import utils
from pkgpanda.util import is_windows

if not is_windows:
    assert 'pwd' in sys.modules

log = logging.getLogger(__name__)


ANYONE_READ = [ACL(Permissions.READ, ANYONE_ID_UNSAFE)]
ANYONE_ALL = [ACL(Permissions.ALL, ANYONE_ID_UNSAFE)]


class Bootstrapper(object):
    def __init__(self, zk_hosts):
        conn_retry_policy = KazooRetry(max_tries=-1, delay=0.1, max_delay=0.1)
        cmd_retry_policy = KazooRetry(max_tries=3, delay=0.3, backoff=1, max_delay=1, ignore_expire=False)
        self._zk = KazooClient(hosts=zk_hosts, connection_retry=conn_retry_policy, command_retry=cmd_retry_policy)

    @property
    def zk(self):
        """Lazy initialize zk client"""
        if self._zk.connected:
            return self._zk
        self._zk.start()
        return self._zk

    def close(self):
        if self._zk.connected:
            self._zk.stop()
            self._zk.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        self.close()

    def cluster_id(self, path, readonly=False):
        dirpath = os.path.dirname(os.path.abspath(path))
        log.info('Opening {} for locking'.format(dirpath))
        with utils.Directory(dirpath) as d:
            log.info('Taking exclusive lock on {}'.format(dirpath))
            with d.lock():
                if readonly:
                    zkid = None
                else:
                    zkid = str(uuid.uuid4()).encode('ascii')

                zkid = self._consensus('/cluster-id', zkid, ANYONE_READ)
                zkid = zkid.decode('ascii')

                if os.path.exists(path):
                    fileid = utils.read_file_line(path)
                    if fileid == zkid:
                        log.info('Cluster ID in ZooKeeper and file are the same: {}'.format(zkid))
                        return zkid

                log.info('Writing cluster ID from ZK to {} via rename'.format(path))

                tmppath = path + '.tmp'
                with open(tmppath, 'w') as f:
                    f.write(zkid + '\n')
                os.rename(tmppath, path)

                log.info('Wrote cluster ID to {}'.format(path))

                return zkid

    def generate_oauth_secret(self, path):
        log.info('Generating oauth secret at {}'.format(path))
        possible_auth_token = ''.join(random.choice(string.ascii_letters) for _ in range(64))
        self.zk.ensure_path('/dcos', ANYONE_ALL)
        consensus_auth_token = self._consensus('/dcos/auth-token-secret',
                                               possible_auth_token.encode('ascii'), ANYONE_READ)
        _write_file(path, consensus_auth_token, 0o600, 'dcos_oauth')
        return consensus_auth_token

    def _consensus(self, path, value, acl=None):
        if value is not None:
            log.info('Reaching consensus about znode {}'.format(path))
            try:
                self.zk.create(path, value, acl=acl)
                log.info('Consensus znode {} created'.format(path))
            except kazoo.exceptions.NodeExistsError:
                log.info('Consensus znode {} already exists'.format(path))
                pass

        self.zk.sync(path)
        return self.zk.get(path)[0]


def _write_file(path, data, mode, owner='root'):
    dirpath = os.path.dirname(os.path.abspath(path))
    log.info('Opening {} for locking'.format(dirpath))
    with utils.Directory(dirpath) as d:
        log.info('Taking exclusive lock on {}'.format(dirpath))
        with d.lock():
            umask_original = os.umask(0)
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                log.info('Writing {} with mode {:o}'.format(path, mode))
                tmppath = path + '.tmp'
                with os.fdopen(os.open(tmppath, flags, mode), 'wb') as f:
                    f.write(data)
                os.rename(tmppath, path)
                if not is_windows:
                    user = pwd.getpwnam(owner)
                    os.chown(path, user.pw_uid, user.pw_gid)
            finally:
                if not is_windows:
                    os.umask(umask_original)
