#!/usr/bin/env python

import argparse
import logging
import subprocess
import sys
from datetime import datetime
from subprocess import CalledProcessError

from dcos_internal_utils import utils


"""Use this node's internal IP address to reach the local CockroachDB instance
and restore the IAM database from a backup.

This program is expected to be executed manually to recover should the IAM
database become corrupt or otherwise require rolling back to a previous
snapshot.
"""


log = logging.getLogger(__name__)
logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')


def recover_database(my_internal_ip: str, backup_file_path: str, db_suffix: str) -> None:
    """Recover the IAM database from `backup_file_path`.

    1. Use `cockroach sql` to create a temporary database called `iam_new`.
    2. Then use `cockroach sql` to load the backup of the IAM database from
       `backup_file_path` into the new database.
    3. Then rename the active `iam` database to `iam_old`.
    4. Finally, rename the `iam_new` database to `iam`.

    If an error occurs at any point the operation is backed out and
    cleaned up. Failure during cleanup results in an error state from
    which manual operator intervention may be required.

    Args:
        my_internal_ip: The internal IP of the current host.
        backup_file_path: A path to a local file containing the SQL backup.
        db_suffix: a date-time (to second) string used to rename databases.
    """
    def _lookup_database(dbname: str) -> None:
        command = [
            '/opt/mesosphere/active/cockroach/bin/cockroach',
            'sql',
            '--insecure',
            '--host={}'.format(my_internal_ip),
            '-e',
            'SHOW TABLES FROM {}'.format(dbname),
            ]
        msg = 'Looking up tables of database `{}` via command `{}`'.format(
            dbname, ' '.join(command))
        log.info(msg)
        try:
            subprocess.run(command, check=True)
            log.info('Database `{}` is present.'.format(dbname))
        except CalledProcessError:
            log.error('Database `{}` is not present.'.format(dbname))
            raise

    def _create_database(dbname: str) -> None:
        command = [
            '/opt/mesosphere/active/cockroach/bin/cockroach',
            'sql',
            '--insecure',
            '--host={}'.format(my_internal_ip),
            '-e',
            'CREATE DATABASE {}'.format(dbname),
            ]
        msg = 'Creating database `{}` via command `{}`'.format(
            dbname, ' '.join(command))
        log.info(msg)
        try:
            subprocess.run(command, check=True)
            log.info("Created database `{}`.".format(dbname))
        except CalledProcessError:
            log.error('Failed to create database `{}`.'.format(dbname))
            raise

    def _load_data(dbname: str, backup_file_path: str) -> None:
        command = [
            '/opt/mesosphere/active/cockroach/bin/cockroach',
            'sql',
            '--insecure',
            '--host={}'.format(my_internal_ip),
            '--database={}'.format(dbname),
            ]
        msg = (
            'Loading backup into database `{}` by '
            'streaming statements over stdin to command `{}`'
            ).format(dbname, ' '.join(command))
        log.info(msg)
        with open(backup_file_path, 'rb') as f:
            try:
                subprocess.run(command, stdin=f, check=True)
                log.info("Successfully loaded data into database `{}`.".format(dbname))
            except CalledProcessError:
                log.error('Failed to load data into database `{}`.'.format(dbname))
                raise

    def _rename_database(oldname: str, newname: str) -> None:
        command = [
            '/opt/mesosphere/active/cockroach/bin/cockroach',
            'sql',
            '--insecure',
            '--host={}'.format(my_internal_ip),
            '-e',
            'ALTER DATABASE {} RENAME to {}'.format(oldname, newname),
            ]
        msg = 'Rename database `{}` to `{}` via command `{}`'.format(
            oldname, newname, ' '.join(command))
        log.info(msg)
        try:
            subprocess.run(command, check=True)
        except CalledProcessError:
            log.error('Failed to rename database `{}` -> `{}`.'.format(oldname, newname))
            raise

    def _drop_database(dbname: str) -> None:
        command = [
            '/opt/mesosphere/active/cockroach/bin/cockroach',
            'sql',
            '--insecure',
            '--host={}'.format(my_internal_ip),
            '-e',
            'DROP DATABASE {}'.format(dbname),
            ]
        msg = 'Drop database `{}` via command `{}`'.format(
            dbname, ' '.join(command))
        log.info(msg)
        try:
            subprocess.run(command, check=True)
            log.info("Removed database `{}`.".format(dbname))
        except CalledProcessError:
            log.error('Failed to drop database')
            raise

    # We add the current date and time as suffix to the database names so this
    # script can be run multiple times.
    iam_new = 'iam_new_{}'.format(db_suffix)
    iam = 'iam'
    iam_old = 'iam_old_{}'.format(db_suffix)

    restore_from_scratch = False
    try:
        _lookup_database(dbname=iam)
    except CalledProcessError:
        log.info('Restoring from scratch (no prior `{}` database)'.format(iam))
        restore_from_scratch = True

    _create_database(dbname=iam_new)
    try:
        _load_data(dbname=iam_new, backup_file_path=backup_file_path)
    except CalledProcessError:
        _drop_database(iam_new)
        raise

    if restore_from_scratch:
        try:
            _rename_database(oldname=iam_new, newname=iam)
        except CalledProcessError:
            _drop_database(iam_new)
            raise
        return

    try:
        _rename_database(oldname=iam, newname=iam_old)
    except CalledProcessError:
        _drop_database(iam_new)
        raise

    try:
        _rename_database(oldname=iam_new, newname=iam)
    except CalledProcessError:
        try:
            _rename_database(oldname=iam_old, newname=iam)
        except CalledProcessError:
            pass
        _drop_database(iam_new)
        raise

    try:
        _drop_database(iam_old)
    except CalledProcessError:
        # Don't raise on failure here as the restore was successful
        log.warning('Failed to remove original (old) database `%s`.', iam_old)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Restore the IAM database from a backup file.')
    parser.add_argument(
        'backup_file_path', type=str,
        help='the path to a file containing the IAM database backup to restore')
    return parser.parse_args()


def main() -> None:
    # Determine the internal IP address of this node.
    my_internal_ip = utils.detect_ip()
    log.info('My internal IP address is `{}`'.format(my_internal_ip))

    args = _parse_args()
    log.info('Backup filepath: {}'.format(args.backup_file_path))

    log.info('Begin IAM database restore procedure.')
    # Add sub-second timestamp resolution to the suffix so that this script can
    # be run twice within a second.
    # See https://jira.mesosphere.com/browse/DCOS-42407
    try:
        recover_database(
            my_internal_ip=my_internal_ip,
            backup_file_path=args.backup_file_path,
            db_suffix=datetime.now().strftime('%Y%m%d_%H%M%S_%f'),
            )
    except subprocess.CalledProcessError:
        log.error("Failed to restore IAM database.")
        sys.exit(1)

    log.info('IAM database restored successfully.')


if __name__ == '__main__':
    main()
