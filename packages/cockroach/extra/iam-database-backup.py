#!/usr/bin/env python

import argparse
import logging
import subprocess
import sys
from typing import IO, Union

from dcos_internal_utils import utils


"""Use this node's internal IP address to reach the local CockroachDB instance
and backup the IAM database.

This program is expected to be executed manually before invasive procedures
such as master replacement or cluster upgrade.
"""


log = logging.getLogger(__name__)
logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')


def dump_database(my_internal_ip: str, out: Union[IO[bytes], IO[str]]) -> None:
    """
    Use `cockroach dump` to dump the IAM database to stdout.

    It is expected that the operator will redirect the output to
    a file or consume it from a backup automation program.

    Args:
        my_internal_ip: The internal IP of the current host.
    """
    command = [
        '/opt/mesosphere/active/cockroach/bin/cockroach',
        'dump',
        '--insecure',
        '--host={}'.format(my_internal_ip),
        'iam',
        ]
    log.info('Dump iam database via command `%s`', ' '.join(command))
    try:
        subprocess.run(command, check=True, stdout=out)
        log.info('Database successfully dumped.')
    except subprocess.CalledProcessError:
        # The stderr output of the underlying cockroach command will be printed
        # to stderr independently.
        log.error('Failed to dump database.')
        # We know the caller isn't doing any cleanup so just exit.
        sys.exit(1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Dump the IAM database to a file.')
    parser.add_argument(
        'backup_file_path', type=str, nargs='?',
        help='the path to a file to which the database backup must be written (stdout if omitted)')
    return parser.parse_args()


def main() -> None:
    # Determine the internal IP address of this node.
    my_internal_ip = utils.detect_ip()
    log.info('My internal IP address is `{}`'.format(my_internal_ip))

    args = _parse_args()
    if args.backup_file_path:
        log.info('Write backup to: {}'.format(args.backup_file_path))
    else:
        log.info('Write backup to: STDOUT')

    if args.backup_file_path:
        with open(args.backup_file_path, 'wb') as f:
            dump_database(my_internal_ip=my_internal_ip, out=f)
    else:
        dump_database(my_internal_ip=my_internal_ip, out=sys.stdout)


if __name__ == '__main__':
    main()
