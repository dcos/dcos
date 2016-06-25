import logging
import os
import uuid

import kazoo.exceptions
from kazoo.client import KazooClient
from kazoo.retry import KazooRetry
from kazoo.security import ACL, ANYONE_ID_UNSAFE, Permissions

from .. import utils

log = logging.getLogger(__name__)


ANYONE_READ = [ACL(Permissions.READ, ANYONE_ID_UNSAFE)]


class Bootstrapper(object):
    def __init__(self, zk_hosts):
        conn_retry_policy = KazooRetry(max_tries=-1, delay=0.1, max_delay=0.1)
        cmd_retry_policy = KazooRetry(max_tries=3, delay=0.3, backoff=1, max_delay=1, ignore_expire=False)
        zk = KazooClient(hosts=zk_hosts, connection_retry=conn_retry_policy, command_retry=cmd_retry_policy)
        zk.start()
        self.zk = zk

    def close(self):
        self.zk.stop()
        self.zk.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        self.close()

    def cluster_id(self, path):
        dirpath = os.path.dirname(os.path.abspath(path))
        log.info('Opening {} for locking'.format(dirpath))
        with utils.Directory(dirpath) as d:
            log.info('Taking exclusive lock on {}'.format(dirpath))
            with d.lock():
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
