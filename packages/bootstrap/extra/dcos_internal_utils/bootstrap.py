import logging
import uuid

import kazoo.exceptions
from kazoo.client import KazooClient
from kazoo.retry import KazooRetry
from kazoo.security import ACL, ANYONE_ID_UNSAFE, Permissions

from dcos_internal_utils import utils

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

    def cluster_id(self, path=utils.dcos_lib_path / 'cluster-id', readonly=False):
        if readonly:
            zkid = None
        else:
            zkid = str(uuid.uuid4()).encode('ascii')
        zkid = self._consensus('/cluster-id', zkid, ANYONE_READ)
        zkid = zkid.decode('ascii')

        path.parent.mkdir(parents=True, exist_ok=True)
        if utils.write_file_on_mismatched_content((zkid + '\n').encode('ascii'), path, utils.write_public_file):
            log.info('Wrote cluster ID to {}'.format(path))
        else:
            log.info('Cluster ID in ZooKeeper and file are the same: {}'.format(zkid))

        return zkid

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
