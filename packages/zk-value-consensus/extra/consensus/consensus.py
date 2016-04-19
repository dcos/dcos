# -*- coding: utf-8 -*-
# Copyright (C) Mesosphere, Inc. See LICENSE file for details.


import argparse
import logging
import os
import platform
import sys
import time
import uuid


import kazoo.exceptions
import kazoo.handlers.threading
from kazoo.client import KazooClient
from kazoo.client import KazooState
from retrying import retry


PAYLOAD_SIZE_LIMIT_BYTES = 1024**2
READ_POLL_INTERVAL_SECONDS = 5


DESCRIPTION = """\
Find consensus about a value through ZooKeeper (ZK).

Read proposal byte sequence from stdin.

Write consensus byte sequence to stdout.
"""


logfmt = "%(asctime)s.%(msecs)03d %(name)s %(levelname)s: %(message)s"
datefmt = "%y%m%d-%H:%M:%S"
logging.basicConfig(format=logfmt, datefmt=datefmt, level=logging.INFO)
log = logging.getLogger()


class ConnectionLost(Exception):
    pass


def main():
    opts = parse_args()

    if not opts.zkpath.startswith('/'):
        sys.exit('ZK path must start with a slash.')

    if opts.zkpath.endswith('/'):
        sys.exit('ZK path must not end with a slash.')

    if opts.readonly:
        log.info('Run in read-only mode.')
        r = ZKNodeReader(
            hoststring=opts.host,
            nodepath=opts.zkpath
            )
        output = r.read()

    else:
        log.info('Read payload from stdin.')
        # Read binary data directly from standard stream.
        payload = sys.stdin.buffer.read()
        log.info('Size of payload data: %s bytes.', len(payload))
        if len(payload) > PAYLOAD_SIZE_LIMIT_BYTES:
            msg = 'Error: payload larger than %s bytes' % (
                PAYLOAD_SIZE_LIMIT_BYTES, )
            sys.exit(msg)

        log.info("Run consensus procedure")
        c = ZKValueConsensus(
            hoststring=opts.host,
            payload=payload,
            nodepath=opts.zkpath
            )
        output = c.achieve_consensus()

    log.info('Write %s bytes to stdout.', len(output))
    # Write binary data directly to standard stream.
    sys.stdout.buffer.write(output)


def retry_read_after_error(exc):
    """Return True if this should be retried."""
    log.info("Observed exception: `%r`", exc)
    if isinstance(exc, kazoo.exceptions.KazooException):
        log.info("Retry as of KazooException.")
        return True
    if isinstance(exc, kazoo.handlers.threading.KazooTimeoutError):
        # https://github.com/python-zk/kazoo/issues/383
        log.info("Retry as of kazoo.handlers.threading.KazooTimeoutError.")
        return True
    log.info("Do not retry.")
    return False


class ZKNodeReader:
    def __init__(self, hoststring, nodepath):
        self._nodepath = nodepath
        self._hosts = hoststring

    def _readloop(self):
        while True:
            try:
                data, stat = self._zk.get(self._nodepath)
                return data, stat
            except kazoo.exceptions.NoNodeError:
                pass
            # TODO(jp): install watch for being fast, and imcrease poll
            # interval.
            log.info(
                "Node `%s` does not yet exist. Retry in %s s.",
                self._nodepath, READ_POLL_INTERVAL_SECONDS)
            time.sleep(READ_POLL_INTERVAL_SECONDS)

    # Wait 2^x * 1000 milliseconds between each retry, up to 64 seconds,
    # then 64 seconds afterwards.
    @retry(
        wait_exponential_multiplier=1000,
        wait_exponential_max=64000,
        retry_on_exception=retry_read_after_error
        )
    def read(self):
        log.info('Set up ZK client using host(s): %s', self._hosts)
        zk = KazooClient(hosts=self._hosts)
        zk.start()
        self._zk = zk
        try:
            # This may raise various kazoo.exceptions.* types.
            data, stat = self._readloop()
        finally:
            log.info('Shut down ZK client.')
            try:
                zk.stop()
            finally:
                zk.close()

        log.info('Foreign payload stat: %s', stat)
        return data


def retry_consensus_after_error(exc):
    """Return True if this should be retried."""

    log.info("Observed exception: `%r`", exc)

    if isinstance(exc, kazoo.exceptions.KazooException):
        log.info("Retry as of KazooException.")
        return True
    if isinstance(exc, ConnectionLost):
        log.info("Retry as of ConnectionLost.")
        return True
    if isinstance(exc, kazoo.handlers.threading.KazooTimeoutError):
        # https://github.com/python-zk/kazoo/issues/383
        log.info("Retry as of kazoo.handlers.threading.KazooTimeoutError.")
        return True
    return False


class ZKValueConsensus:
    """A helper class for achieving consensus across multiple parties, using
    the ZK distributed lock recipe as coordination mechanism.

    Every contributing party uses the same `nodepath`, proposes its own value
    (`payload`), and eventually all parties proceed using the same value,
    which is one of the proposed ones.
    """

    def __init__(self, hoststring, payload, nodepath):
        self._nodepath = nodepath
        self._payload = payload
        self._hosts = hoststring

        # Use current hostname as ZK lock contender identifier, plus some
        # random bytes.
        self._identifier = platform.node() + '-' + str(uuid.uuid4())[:8]

    # Wait 2^x * 1000 milliseconds between each retry, up to 64 seconds,
    # then 64 seconds afterwards.
    @retry(
        wait_exponential_multiplier=1000,
        wait_exponential_max=64000,
        retry_on_exception=retry_consensus_after_error
        )
    def achieve_consensus(self):
        """Trigger consensus logic and handle errors."""

        log.info('Set up ZK client using host(s): %s', self._hosts)
        zk = KazooClient(hosts=self._hosts)

        # Initialize ZK connection state variable, which is shared across
        # threads. It is updated from a change listener function which is
        # invoked from within a Kazoo connection management thread, see
        # http://kazoo.readthedocs.org/en/latest/api/handlers/threading.html.
        self._connected = False
        zk.add_listener(self._zk_state_change_listener)
        zk.start()

        # Wait for handling thread to update connection status. (As of non-
        # determinism around GIL context switches there is otherwise no
        # guarantee that the status is updated within
        # `_run_consensus_procedure`).
        while not self._connected:
            time.sleep(0.01)

        self._zk = zk
        try:
            # This may raise ConnectionLost or various
            # kazoo.exceptions.* types.
            return self._run_consensus_procedure()
        finally:
            log.info('Shut down ZK client.')
            try:
                zk.stop()
            finally:
                zk.close()

    def _run_consensus_procedure(self):
        """
        Normal operation:
            - Acquire distributed lock.
            - Attempt to create node.
            - If creation fails because node is already existing, then read
              data and return it. If creation succeeds, return corresponding
              value.
            - Before returning, release the lock.

        Handling of unexpected events:
            - If the distributed lock acquisition times out, repeat,
              endlessly, in a loop.
            - If the ZK connection state degrades, raise `ConnectionLost`,
              to be handled on a higher level.
            - No other magic is performed, so any kazoo exception thrown
              needs to handled on a higher level.
        """
        head, tail = os.path.split(self._nodepath)
        lockpath = os.path.join(head, 'lock')
        lock = self._zk.Lock(path=lockpath, identifier=self._identifier)

        while True:
            if not self._connected:
                raise ConnectionLost
            timed_out = False
            try:
                log.info("Attempt to acquire distributed lock.")
                lock.acquire(timeout=7)
                log.info("Distributed lock acquired.")
                return self._set_or_read()
            except kazoo.exceptions.LockTimeout:
                log.info("Distributed lock acquisition timed out. Retry.")
                timed_out = True
            finally:
                if not timed_out:
                    # Release lock, clean up.
                    log.info("Release distributed lock.")
                    lock.release()
                else:
                    # No cleanup required as lock acquisition timed out.
                    pass

    def _set_or_read(self):
        # Execute under distributed lock protection.

        log.info('Attempt to create node `%s`.', self._nodepath)

        try:
            self._zk.create(
                path=self._nodepath, value=self._payload, makepath=True)
            log.info('Node creation succeeded, return "my" payload.')
            return self._payload
        except kazoo.exceptions.NodeExistsError:
            log.info('Node exists. Read it.')
            data, stat = self._zk.get(self._nodepath)
            log.info('Foreign payload stat: %s', stat)
            return data

    def _zk_state_change_listener(self, state):
        """
        'When using the kazoo.recipe.lock.Lock or creating ephemeral nodes,
        its highly recommended to add a state listener so that your program
        can properly deal with connection interruptions or a Zookeeper session
        loss.'

        This is executed in the
        kazoo.handlers.threading.SequentialThreadingHandler
        """

        if state == KazooState.LOST:
            log.info('Connection state is KazooState.LOST')
            self._connected = False
        elif state == KazooState.SUSPENDED:
            log.info('Connection state is KazooState.SUSPENDED')
            self._connected = False
        else:
            # CONNECTED state.
            log.info('Connection state is KazooState.CONNECTED')
            self._connected = True


def parse_args():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION)
    parser.add_argument(
        'zkpath',
        type=str,
        help='The ZK node path to sync on.'
        )
    parser.add_argument(
        '--host',
        type=str,
        default='127.0.0.1:2181',
        help=('Host string passed to Kazoo client constructor. '
              'Default: 127.0.0.1:2181'))
    parser.add_argument(
        '--read',
        dest='readonly',
        action='store_true',
        default=False,
        help=('Only read (do not contribute to consensus). Wait until node '
              'exists, and return data to stdout.'))
    return parser.parse_args()
