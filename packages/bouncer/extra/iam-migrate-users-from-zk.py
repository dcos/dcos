#!/usr/bin/env python

"""
This is a users migration script from DC/OS Open 1.12 where users were stored
in ZK database.

The migration scripts creates an IAM user for each legacy user and deletes
the legacy user from ZK. After the migration is completed the /dcos/users
path is deleted completely.

Notes:
This script should be removed from future versions of DC/OS Open.
When removing this script also remove `python-kazoo` dependency from the
`bouncer-deps` DC/OS package.
"""

import logging
from typing import List


import kazoo.exceptions
import requests
from kazoo.client import KazooClient
from kazoo.retry import KazooRetry


log = logging.getLogger(__name__)
logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')


# This script will run on a master server after the IAM service has been running.
ZK_HOSTS = 'zk-1.zk:2181,zk-2.zk:2181,zk-3.zk:2181,zk-4.zk:2181,zk-5.zk:2181'
ZK_USERS_PATH = '/dcos/users'
# To keep this script simple and avoid authentication and authorization this
# script uses local IAM address instead of going through Admin Router
IAM_BASE_URL = 'http://127.0.0.1:8101'


def create_zk_client(zk_hosts: str) -> KazooClient:
    conn_retry_policy = KazooRetry(max_tries=-1, delay=0.1, max_delay=0.1)
    cmd_retry_policy = KazooRetry(
        max_tries=3, delay=0.3, backoff=1, max_delay=1, ignore_expire=False)
    return KazooClient(
        hosts=zk_hosts,
        connection_retry=conn_retry_policy,
        command_retry=cmd_retry_policy,
    )


def get_legacy_uids_from_zk(zk: KazooClient) -> List:
    """
    Loads users from legacy datastore

    https://github.com/dcos/dcos-oauth/blob/ac186bf48f21166c3bb935fdc1922bbace75b6a4/dcos-oauth/users.go
    """
    return zk.get_children(ZK_USERS_PATH)


def migrate_user(uid: str) -> None:
    """
    Create a user in IAM service:

    https://github.com/dcos/dcos/blob/abaeb5cceedd5661b8d96ff47f8bb5ef212afbdc/packages/dcos-integration-test/extra/test_legacy_user_management.py#L96
    """
    url = '{iam}/acs/api/v1/users/{uid}'.format(
        iam=IAM_BASE_URL,
        uid=uid,
    )
    r = requests.put(url, json={})

    # The 409 response code means that user already exists in the DC/OS IAM
    # service
    if r.status_code == 409:
        log.info('Skipping existing IAM user `%s`', uid)
        return
    else:
        r.raise_for_status()

    log.info('Created IAM user `%s`', uid)


def main() -> None:
    log.info('Initialize ZK client')
    zk = create_zk_client(zk_hosts=ZK_HOSTS)
    zk.start()

    # If a cluster is not being upgraded or a migration has been already
    # performed fail fast
    if not zk.exists(ZK_USERS_PATH):
        log.info(
            'Path `%s` does not exits in ZK. Nothing to migrate.', ZK_USERS_PATH)
        return

    # Check that the IAM service is up and running with a simple health check
    r = requests.get('{iam}/acs/api/v1/auth/jwks'.format(
        iam=IAM_BASE_URL,
    ))
    assert r.status_code == 200

    uids = get_legacy_uids_from_zk(zk=zk)
    log.info('Found `%d` users for migration.', len(uids))

    for uid in uids:
        log.info('Migrating uid `%s`', uid)
        migrate_user(uid=uid)

        zk_uid_path = '{base_path}/{uid}'.format(
            base_path=ZK_USERS_PATH,
            uid=uid
        )
        try:
            log.info('Deleting ZK path `%s`', zk_uid_path)
            zk.delete(zk_uid_path)
        except kazoo.exceptions.NoNodeError:
            # It is possible that the user was removed by another master running
            # this script.
            log.warn('ZK node `%s` no longer exists.', zk_uid_path)

    # Finally we can remove /dcos/users which should be empty at this point
    try:
        log.info('Removing legacy ZK path `%s`.', ZK_USERS_PATH)
        zk.delete(ZK_USERS_PATH)
    except kazoo.exceptions.NoNodeError:
        # It is possible that the user was removed by another master running
        # this script.
        log.warn('ZK node `%s` no longer exists.', ZK_USERS_PATH)

    zk.stop()
    log.info('Migration completed.')


if __name__ == "__main__":
    main()
