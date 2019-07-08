#!/usr/bin/env python3
"""
Command line tool for automated DC/OS ZooKeeper instance backup and restore.

This script is made available as `dcos-zk` executable in DC/OS.

"""
import shlex
import shutil
import subprocess
import sys
import tarfile
from argparse import ArgumentParser, ArgumentTypeError
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional


EXHIBITOR_DIR = Path('/var/lib/dcos/exhibitor')


def run_command(cmd: str, verbose: bool) -> None:
    """
    Run a command in a subprocess.

    Args:
        verbose: Show the output.

    Raises:
        subprocess.CalledProcessError: The given cmd exits with a non-0 exit code.
    """
    stdout = None if verbose else subprocess.PIPE
    stderr = None if verbose else subprocess.STDOUT
    subprocess.run(
        args=shlex.split(cmd),
        stdout=stdout,
        stderr=stderr,
        check=True,
    )


def _is_zookeeper_running(verbose: bool) -> bool:
    """
    Returns whether the ZooKeeper process that Exhibitor controls is running.
    """
    zk_pid_file = Path('/var/lib/dcos/exhibitor/zk.pid')
    zk_pid = int(zk_pid_file.read_text())
    try:
        # Check whether the ZooKeeper that Exhibitor controls is running.
        run_command('kill -0 {zk_pid}'.format(zk_pid=zk_pid), verbose)
    except subprocess.CalledProcessError:
        # Exit code 1 indicates that ZooKeeper is dead.
        return False
    return True


def _copy_dir_and_preserve_ownership(src: Path, dst: Path, verbose: bool) -> None:
    """
    Copy a directory from ``src`` to ``dst`` and preserve ownership.

    We need to preserve ownership for a successful restore.
    We use a subprocess (with `cp -p`) for this rather than Python's
    `shutil.copytree` as `copytree` does not preserve ownership.
    """
    run_command('cp -prv {src} {dst}'.format(src=src, dst=dst), verbose)


def backup_zookeeper(
    backup: Path,
    tmp_dir: Path,
    verbose: bool,
) -> None:
    """
    DC/OS ZooKeeper instance backup procedure.

    ZooKeeper changes files while it is running.  In order to have a consistent
    backup stop ZooKeeper, run the backup procedure, then start ZooKeeper.

    See https://jira.mesosphere.com/browse/DCOS_OSS-5185
    for changing this procedure to allow a backup without downtime.

    If backing up ZooKeeper via a custom temporary directory, a failing backup
    procedure does not clean up files created in the temporary directory in the
    process.
    """
    zookeeper_dir = EXHIBITOR_DIR / 'zookeeper'
    tmp_zookeeper_dir = tmp_dir / 'zookeeper'

    print('Backing up ZooKeeper into {backup} via {tmp_zookeeper_dir}'.format(
        backup=backup,
        tmp_zookeeper_dir=tmp_zookeeper_dir,
    ))

    print('Validate that ZooKeeper is not running')
    if _is_zookeeper_running(verbose):
        sys.stderr.write('ZooKeeper must not be running. Aborting.\n')
        sys.exit(1)

    print('Copying ZooKeeper files to {tmp_zookeeper_dir}'.format(
        tmp_zookeeper_dir=tmp_zookeeper_dir,
    ))

    _copy_dir_and_preserve_ownership(
        src=zookeeper_dir,
        dst=tmp_zookeeper_dir,
        verbose=verbose,
    )

    print('Creating ZooKeeper backup tar archive at {backup}'.format(backup=backup))

    def _tar_filter(tar_info: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
        # The myid file is not backed up because it identifies the local
        # ZooKeeper instance and is automatically recreated on start up.
        if 'myid' in tar_info.name:
            return None
        # The `zookeeper.out` contains ZooKeeper logs written to `stdout`.
        # These take up space and are irrelevant to the backup procedure.
        if 'zookeeper.out' in tar_info.name:
            return None
        return tar_info

    with tarfile.open(name=str(backup), mode='x:gz') as tar:
        tar.add(
            name=str(tmp_zookeeper_dir),
            arcname='./zookeeper',
            filter=_tar_filter,
        )
        if verbose:
            tar.list()

    print('Deleting temporary files in {tmp_zookeeper_dir}'.format(
        tmp_zookeeper_dir=tmp_zookeeper_dir,
    ))
    shutil.rmtree(path=str(tmp_zookeeper_dir), ignore_errors=True)

    print('ZooKeeper backup taken successfully')


def restore_zookeeper(backup: Path, tmp_dir: Path, verbose: bool) -> None:
    """
    DC/OS ZooKeeper restore from backup procedure.

    ZooKeeper changes files while it is running.
    In order to have a consistent restore, one must stop ZooKeeper on all
    master nodes, execute this procedure on all master nodes, and then start
    ZooKeeper again on all master nodes.

    Stopping ZooKeeper on all master nodes inevitably causes the DC/OS cluster
    to experience downtime.  The restore procedure is intended for recovering
    from an unusable DC/OS cluster as a last resort measure.

    Running this script requires at least as much free space as the ZooKeeper backup takes.
    """
    zookeeper_dir = EXHIBITOR_DIR / 'zookeeper'
    tmp_zookeeper_dir = tmp_dir / 'zookeeper'

    print('Restoring local ZooKeeper instance from {backup}'.format(backup=backup))

    print('Validate that ZooKeeper is not running')
    if _is_zookeeper_running(verbose):
        # We believe that this may be hit during tests when ZooKeeper is not running.
        # If the case ever appears where Exhibitor is not running but ZooKeeper is
        # we must reconsider our assumptions about Exhibitor properly controlling
        # the ZooKeeper process.
        #
        # The test in question is
        # `TestZooKeeperBackup.test_transaction_log_backup_and_restore` and
        # this test stops the Exhibitor process.  We assume in that test that
        # by the time `systemctl stop` returns, ZooKeeper is stopped. However,
        # we suspect that this may not be the case every single time. If it is
        # not the case we will get here in that test.
        #
        # See https://jira.mesosphere.com/browse/DCOS-55827 for details.
        sys.stderr.write('ZooKeeper must not be running. Aborting.\n')
        sys.exit(1)

    print('Moving ZooKeeper files temporarily to {tmp_zookeeper_dir}'.format(
        tmp_zookeeper_dir=tmp_zookeeper_dir,
    ))
    # We copy files rather than move them so that if this script is interrupted
    # while running, no data is lost inplace.
    # However, this has a downside that we may use a lot of disk space -
    # we have seen ZooKeeper files up to 20 GB in size.
    _copy_dir_and_preserve_ownership(
        src=zookeeper_dir,
        dst=tmp_zookeeper_dir,
        verbose=verbose,
    )
    shutil.rmtree(path=str(zookeeper_dir))

    print('Restoring {zookeeper_dir} from backup {backup}'.format(
        zookeeper_dir=zookeeper_dir,
        backup=backup,
    ))
    with tarfile.open(name=str(backup), mode='r:gz') as tar:
        tar.extractall(path=str(EXHIBITOR_DIR))
        if verbose:
            tar.list()

    print('Deleting temporary files in {tmp_zookeeper_dir}'.format(
        tmp_zookeeper_dir=tmp_zookeeper_dir,
    ))
    shutil.rmtree(path=str(tmp_zookeeper_dir), ignore_errors=True)

    print('Local ZooKeeper instance restored successfully')


def _non_existing_file_path_existing_parent_dir(value: str) -> Path:
    """
    Validate that the value is a path to a file which does not exist
    but the parent directory tree exists.
    """
    path = Path(value)
    if path.exists():
        raise ArgumentTypeError('{} already exists'.format(path))
    if not Path(path.parent).exists():
        raise ArgumentTypeError(
            '{} parent directory does not exist'.format(path),
        )
    return path.absolute()


def _existing_file_path(value: str) -> Path:
    """
    Validate that the value is a file which does exist on the file system.
    """
    path = Path(value)
    if not path.exists():
        raise ArgumentTypeError('{} does not exist'.format(path))
    if not path.is_file():
        raise ArgumentTypeError('{} is not a file'.format(path))
    return path.absolute()


def _existing_dir_path(value: str) -> Path:
    """
    Validate that the value is a directory which does exist on the file system.
    """
    path = Path(value)
    if not path.exists():
        raise ArgumentTypeError('{} does not exist'.format(path))
    if not path.is_dir():
        raise ArgumentTypeError('{} is not a directory'.format(path))
    return path.absolute()


class DCOSZooKeeperCli:
    """
    Minimal CLI to backup/restore the local DC/OS ZooKeeper instance.
    """

    def __init__(self) -> None:
        """
        Present CLI command choices.
        """
        parser = ArgumentParser(
            description=(
                'Command line utility to backup and restore the local '
                'ZooKeeper instance on DC/OS master nodes.'
            )
        )
        parser.add_argument(
            'command',
            type=str,
            choices=[
                'backup',
                'restore',
            ],
            help='CLI commands available',
        )
        args = parser.parse_args(sys.argv[1:2])
        getattr(self, args.command)()

    def backup(self) -> None:
        """
        Procedure invoked on `backup` command.
        """
        parser = ArgumentParser(
            usage=(
                '{executable} backup [-h] [-t TMP_DIR] [-v] backup_path'
            ).format(executable=sys.argv[0]),
            description=(
                'Create a backup of the ZooKeeper instance running on this '
                'DC/OS master node.'
            ),
        )
        parser.add_argument(
            'backup_path',
            type=_non_existing_file_path_existing_parent_dir,
            help=(
                'File path that the gzipped ZooKeeper backup tar archive will '
                'be written to.'
            ),
        )
        parser.add_argument(
            '-t', '--tmp-dir',
            type=_existing_dir_path,
            help=(
                'Location of an existing directory to be used as temporary '
                'directory. A temporary directory will be created if not '
                'specified.'
            ),
        )
        parser.add_argument(
            '-v', '--verbose',
            action='store_true',
            help='Display the output of every command.',
        )
        args = parser.parse_args(sys.argv[2:])
        if args.tmp_dir is None:
            with TemporaryDirectory(suffix='-zk-backup') as tmp_dir:
                backup_zookeeper(
                    backup=args.backup_path,
                    tmp_dir=Path(tmp_dir),
                    verbose=args.verbose,
                )
        else:
            backup_zookeeper(
                backup=args.backup_path,
                tmp_dir=args.tmp_dir,
                verbose=args.verbose,
            )

    def restore(self) -> None:
        """
        Procedure invoked on `restore` command.
        """
        parser = ArgumentParser(
            usage=(
                '{executable} restore [-h] [-t TMP_DIR] [-v] backup_path'
            ).format(executable=sys.argv[0]),
            description=(
                'Restore the ZooKeeper instance running on this DC/OS master '
                'node from the given backup.'
            ),
        )
        parser.add_argument(
            'backup_path',
            type=_existing_file_path,
            help=(
                'File path to the gzipped ZooKeeper backup tar archive to '
                'restore from.'
            ),
        )
        parser.add_argument(
            '-t', '--tmp-dir',
            type=_existing_dir_path,
            help=(
                'Location of an existing directory to be used as temporary '
                'directory. A temporary directory will be created if not '
                'specified.'
            ),
        )
        parser.add_argument(
            '-v', '--verbose',
            action='store_true',
            help='Display the output of every command',
        )
        args = parser.parse_args(sys.argv[2:])
        if args.tmp_dir is None:
            with TemporaryDirectory(suffix='-zk-restore') as tmp_dir:
                restore_zookeeper(
                    backup=args.backup_path,
                    tmp_dir=Path(tmp_dir),
                    verbose=args.verbose,
                )
        else:
            restore_zookeeper(
                backup=args.backup_path,
                tmp_dir=args.tmp_dir,
                verbose=args.verbose,
            )


if __name__ == '__main__':
    try:
        DCOSZooKeeperCli()
    except subprocess.CalledProcessError as exc:
        if exc.output:
            sys.stdout.buffer.write(exc.output)
        sys.exit(exc.returncode)
