"""
Tests automated migration script for users stored by dcos-oauth service
"""

import logging
import time
from subprocess import check_call
from typing import Any, Generator

import kazoo.exceptions
import pytest
from dcos_test_utils.dcos_api import DcosApiSession
from kazoo.client import KazooClient
from kazoo.retry import KazooRetry


__maintainer__ = 'mhrabovcin'
__contact__ = 'security-team@mesosphere.io'


log = logging.getLogger(__name__)


@pytest.fixture(scope='module')
def zk() -> KazooClient:
    conn_retry_policy = KazooRetry(max_tries=-1, delay=0.1, max_delay=0.1)
    cmd_retry_policy = KazooRetry(
        max_tries=3, delay=0.3, backoff=1, max_delay=1, ignore_expire=False)
    zk = KazooClient(
        hosts='zk-1.zk:2181,zk-2.zk:2181,zk-3.zk:2181',
        connection_retry=conn_retry_policy,
        command_retry=cmd_retry_policy,
    )
    zk.start()
    yield zk
    zk.stop()


@pytest.fixture()
def create_dcos_oauth_users(zk: KazooClient) -> Generator:

    def _create_dcos_oauth_user(uid: str) -> None:
        log.info('Creating user `%s`', uid)
        zk.create('/dcos/users/{uid}'.format(uid=uid), makepath=True)

    def _delete_dcos_oauth_user(uid: str) -> None:
        try:
            zk.delete('/dcos/users/{uid}'.format(uid=uid))
        except kazoo.exceptions.NoNodeError:
            pass

    _create_dcos_oauth_user('user1@example.com')
    _create_dcos_oauth_user('user2@example.com')

    yield

    _delete_dcos_oauth_user('user1@example.com')
    _delete_dcos_oauth_user('user2@example.com')


@pytest.mark.usefixtures('create_dcos_oauth_users')
def test_iam_migration(dcos_api_session: DcosApiSession) -> None:
    check_call(['sudo', 'systemctl', 'stop', 'dcos-bouncer-migrate-users.service'])

    def _filter_test_uids(r: Any) -> list:
        return [
            u['uid'] for u in r.json()['array'] if '@example.com' in u['uid']]

    r = dcos_api_session.get('/acs/api/v1/users')
    test_uids = _filter_test_uids(r)
    assert len(test_uids) == 0

    check_call(['sudo', 'systemctl', 'start', 'dcos-bouncer-migrate-users.service'])
    # Sleep for 5 seconds and let the migration script run
    time.sleep(5)

    r = dcos_api_session.get('/acs/api/v1/users')
    test_uids = _filter_test_uids(r)
    assert len(test_uids) == 2
    assert 'user1@example.com' in test_uids
    assert 'user2@example.com' in test_uids
