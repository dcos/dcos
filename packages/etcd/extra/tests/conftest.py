import logging

import pytest
from kazoo.client import KazooClient
from kazoo.handlers.threading import SequentialThreadingHandler
from kazoo.retry import KazooRetry
from kazoo.security import ACL, ANYONE_ID_UNSAFE, Permissions


@pytest.fixture(scope="session")
def zk_conn():
    conn_retry_policy = KazooRetry(max_tries=-1,
                                   delay=0.1,
                                   backoff=2,
                                   max_delay=3600)
    handler = SequentialThreadingHandler()
    conn = KazooClient(hosts="127.0.0.1:2181",
                       timeout=60,
                       handler=handler,
                       connection_retry=conn_retry_policy,
                       command_retry=conn_retry_policy)

    conn.start()
    yield conn
    conn.stop()


@pytest.fixture(scope="function")
def zk(zk_conn):
    # FIXME(prozlach): Let's narrow down this permisssions to better reflect
    # what bootstrap script is doing. This requires some research wrt the IP
    # we are connecting from to the container
    # acl = LOCALHOST_ALL + [self.make_service_acl('dcos_etcd', all=True)]
    anyone_all = [ACL(Permissions.ALL, ANYONE_ID_UNSAFE)]

    zk_conn.ensure_path('/etcd', acl=anyone_all)
    zk_conn.ensure_path('/etcd/nodes', acl=anyone_all)
    zk_conn.set('/etcd/nodes', b"")
    zk_conn.ensure_path('/etcd/locking', acl=anyone_all)
    zk_conn.set('/etcd/locking', b"")

    yield zk_conn

    zk_conn.delete('/etcd', recursive=True)


def pytest_configure(config):
    logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')
