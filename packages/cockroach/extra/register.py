#!/usr/bin/env python

"""Start CockroachDB.

CockroachDB clusters need to be bootstrapped.

This is done by starting the very first node without the
--join=<ip1,ip2,...,ipN> parameter. Once bootstrapped, no node must
ever be started without the --join parameter again, doing so would
initialize a new cluster causing the old cluster to be effectively
discarded.

This poses an interesting problem for us as it means we need to know whether a
cluster has been bootstrapped before, from any of the masters in the cluster.

Additionally, once a cluster has been bootstrapped by starting a node in this
"initial master mode" all subsequent nodes need to be started with one or more
peer IP addresses provided to them via the --join<ip1,ip2,...,ipN> parameter.

As this list of IPs is used for discovery through the gossip protocol, not all
the provided IP addresses actually need to be up or reachable (that would
introduce a chicken and egg problem, anyway.) An example bootstrap sequence
would be:

node1:
./cockroach

node2:
./cockroach --join=node1

node3:
./cockroach --join=node1,node2

Then, after any crashes or server reboots, any of these nodes can be started
with the following command and they will discover one another:

./cockroach --join=node1,node2,node3

Here we have used the hostname of the nodes (node1, node2, etc.) but for DC/OS
we would use the internal IP addresses of the master nodes instead.

CockroachDB also supports a --pid-file parameter which writes the PID to
a file once the server is ready to serve requests.

The bootstrap and discovery strategy we designed is as follows:

1. Connect to ZooKeeper.

2. Determine whether the cluster has already been initialized by
  checking whether the list of IPs at `ZK_NODES_PATH` exists. This
  does not require the lock to be held as nodes can only ever be
  added, never removed: if the list of IPs at `ZK_NODES_PATH` is
  non-empty, we know the cluster has been bootstrapped.

3. If the list is empty:

3.1 Take and hold the ZK lock.

3.2 Check the `ZK_NODES_PATH` again to ensure the value hasn't been
    updated since we checked it in step 2.

3.3 If it is now non-empty goto step 4 as the cluster has since been initialized.

3.4 If it is still empty, we need to bootstrap the cluster.

3.5 Start CockroachDB without the --join=... parameter to initialize
    the new cluster. Stop it again.

3.6 Add the current node's IP address to the list at `ZK_NODES_PATH`.

3.7 Release the lock, write the list of nodes to `NODES_PATH_FILE` and exit 0.

4. If `ZK_NODES_PATH` is non-empty:

4.1 If our IP is not yet in the list, briefly take the ZK lock and add
    our IP to ZK. Release the lock.

4.2 Write the list of node IPs to `NODES_PATH_FILE` and exit 0.

4.3 Exit 0. The cockroach.sh script will exec the cockroach service with
    the --join parameter taken from `NODES_PATH_FILE`.

See
https://jira.mesosphere.com/browse/DCOS-16183 and then
https://jira.mesosphere.com/browse/DCOS-17886 and then
https://jira.mesosphere.com/browse/DCOS-17325

Note that for long-running processes using Kazoo and especially Kazoo's lock
recipe it is recommended to add a connection state change event handler that
takes care of communicating the current connection state to the rest of the
application so that it can respond to it (which enables e.g. delayed lock
release). This process here, however, is shortlived. Errors that occur during
ZooKeeper interaction lead to an application crash. In that case (when this
program exits with a non-zero exit code) the outer systemd wrapper makes sure
that potentially orphaned child processes (CockroachDB!) are killed and reaped.
"""

import json
import logging
import os
import pwd
import socket
import subprocess
from contextlib import contextmanager
from typing import Any, Generator, List, Optional

import requests
import retrying

from kazoo.client import KazooClient
from kazoo.exceptions import (
    ConnectionLoss,
    LockTimeout,
    SessionExpiredError,
)
from kazoo.retry import KazooRetry
from kazoo.security import make_digest_acl
from requests import ConnectionError, HTTPError, Timeout

from dcos_internal_utils import utils


log = logging.getLogger(__name__)


def zk_connect(zk_user: Optional[str] = None, zk_secret: Optional[str] = None) -> KazooClient:
    """Connect to ZooKeeper.

    On connection failure, the function attempts to reconnect indefinitely with exponential backoff
    up to 3 seconds. If a command fails, that command is retried every 300ms for 3 attempts before failing.

    These values are chosen to suit a human-interactive time.

    Args:
        zk_user:
            The username to use when connecting to ZooKeeper or `None` if no authentication is necessary.
        zk_secret:
            The secret to use when connecting to ZooKeeper or `None` if no authentication is necessary.

    Returns:
        A ZooKeeper client connection in the form of a `kazoo.client.KazooClient`.
    """
    # Try to reconnect indefinitely, with time between updates going
    # exponentially to ~3s. Then every retry occurs every ~3 seconds.
    conn_retry_policy = KazooRetry(
        max_tries=-1,
        delay=0.3,
        backoff=1.3,
        max_jitter=1,
        max_delay=3,
        ignore_expire=True,
    )
    # Retry commands every 0.3 seconds, for a total of <1s (usually 0.9)
    cmd_retry_policy = KazooRetry(
        max_tries=3,
        delay=0.3,
        backoff=1,
        max_jitter=0.1,
        max_delay=1,
        ignore_expire=False,
        )
    default_acl = None
    auth_data = None
    if zk_user and zk_secret:
        default_acl = [make_digest_acl(zk_user, zk_secret, all=True)]
        scheme = 'digest'
        credential = "{}:{}".format(zk_user, zk_secret)
        auth_data = [(scheme, credential)]
    zk = KazooClient(
        hosts="127.0.0.1:2181",
        timeout=30,
        connection_retry=conn_retry_policy,
        command_retry=cmd_retry_policy,
        default_acl=default_acl,
        auth_data=auth_data,
        )
    zk.start()
    return zk


# The prefix used for cockroachdb in ZK.
ZK_PATH = "/cockroach"
# The path of the ZNode used for locking.
ZK_LOCK_PATH = ZK_PATH + "/lock"
# The path of the ZNode containing the list of cluster members.
ZK_NODES_PATH = ZK_PATH + "/nodes"
# The id to use when contending for the ZK lock.
LOCK_CONTENDER_ID = "{hostname}:{pid}".format(
    hostname=socket.gethostname(),
    pid=os.getpid(),
    )
# The path to the CockroachDB PID file.
PID_FILE_PATH = '/run/dcos/cockroach/cockroach.pid'
# The path to the file containing the list of nodes in the cluster as a
# comma-separated list of IPs.
NODES_FILE_PATH = '/run/dcos/cockroach/nodes'
# The time in seconds to wait when attempting to acquire a lock.  Lock
# acquisition between 5 ZooKeeper nodes is an operation on the order
# of milliseconds.
#
# Furthermore, the operations performed while the lock is held are
# performed once and never again. This means a process will only
# contend for the lock once. As such, if lock aquisition fails due to
# some other process holding it, the current process will crash and be
# restarted with one less contender for the same lock. This means that
# the locking behaviour does converge and no timeout-sensitive
# livelock can occur.
#
# We set the lock timeout to a couple of seconds instead of
# milliseconds to account for variation in network latency between
# nodes in the cluster. The current value has so far shown to be
# sufficient.
ZK_LOCK_TIMEOUT = 5


@contextmanager
def _zk_lock(zk: KazooClient, lock_path: str, contender_id: str, timeout: int) -> Generator:
    """
    This contextmanager takes a ZooKeeper lock, yields, then releases
    the lock. This lock behaves like an interprocess mutex lock.

    ZooKeeper allows one to read values without holding a lock, but
    there is no guarantee that you will read the latest value. To read
    the latest value, you must call `sync()` on a ZNode before calling
    `get()`.

    Args:
        zk:
            The client to use to communicate with ZooKeeper.
        lock_path:
            The ZNode path to use as prefix for the locking recipe.
        contender_id:
            The contender id to identify the current client
            in the locking recipe.
        timeout:
            Time in seconds to wait for the lock to be acquired.
            If this time elapses before the lock is acquired, a
            `kazoo.exceptions.LockTimeout` exception is raised.

    Raises:
        kazoo.exceptions.LockTimeout:
            If the `timeout` is exceeded without the lock being acquired.

    """
    lock = zk.Lock(lock_path, contender_id)
    try:
        log.info("Acquiring ZooKeeper lock.")
        lock.acquire(blocking=True, timeout=timeout)
    except (ConnectionLoss, SessionExpiredError) as e:
        msg_fmt = "Failed to acquire lock: {}"
        msg = msg_fmt.format(e.__class__.__name__)
        log.exception(msg)
        raise e
    except LockTimeout as e:
        msg_fmt = "Failed to acquire lock in `{}` seconds"
        msg = msg_fmt.format(timeout)
        log.exception(msg)
        raise e
    else:
        log.info("ZooKeeper lock acquired.")
    yield
    log.info("Releasing ZooKeeper lock")
    lock.release()
    log.info("ZooKeeper lock released.")


def _init_cockroachdb_cluster(ip: str) -> None:
    """
    Starts CockroachDB listening on `ip`. It waits until the cluster ID is
    published via the local gossip endpoint, signalling that the instance has
    successfully initialized the cluster. Thereafter it shuts down the
    bootstrap CockroachDB instance again.

    Args:
        ip:
            The IP that CockroachDB should listen on.
            This should be the internal IP of the current host.
    """
    # We chose 1 second as a time to wait between retries.
    # If we chose a value longer than this, we could wait for up to <chosen
    # value> too long between retries, delaying the cluster start by up to that
    # value.
    #
    # The more often we run this function, the more logs we generate.
    # If we chose a value smaller than 1 second, we would therefore generate more logs.
    # We consider 1 second to be a reasonable maximum delay and in our
    # experience the log size has not been an issue.
    wait_fixed_ms = 1000

    # In our experience, the cluster is always initialized within one minute.
    # The downside of having a timeout which is too short is that we may crash
    # when the cluster was on track to becoming healthy.
    #
    # The downside of having a timeout which is too long is that we may wait up
    # to that timeout to see an error.
    #
    # We chose 5 minutes as trade-off between these two, as we think that it
    # is extremely unlikely that a successful initialization will take more
    # than 5 minutes, and we think that waiting up to 5 minutes "too long"
    # for an error (and accumulating 5 minutes of logs) is not so bad.
    stop_max_delay_ms = 5 * 60 * 1000

    @retrying.retry(
        wait_fixed=wait_fixed_ms,
        stop_max_delay=stop_max_delay_ms,
        retry_on_result=lambda x: x is False,
    )
    def _wait_for_cluster_init() -> bool:
        """
        CockroachDB Cluster initialization takes a certain amount of time
        while the cluster ID and node ID are written to the storage.

        If after 5 minutes of attempts the cluster ID is not available raise an
        exception.
        """
        gossip_url = 'http://localhost:8090/_status/gossip/local'

        # 3.05 is a magic number for the HTTP ConnectTimeout.
        # http://docs.python-requests.org/en/master/user/advanced/#timeouts
        # The rationale is to set connect timeouts to slightly larger than a multiple of 3,
        # which is the default TCP packet retransmission window.
        # 27 is the ReadTimeout, taken from the same example.
        connect_timeout_seconds = 3.05

        # In our experience, we have not seen a read timeout of > 1 second.
        # If this were extremely long, we may have to wait up to that amount of time to see an error.
        # If this were too short, and for example CockroachDB were spending a long time to respond
        # because it is busy or on slow hardware, we may retry this function
        # even when the cluster is initialized.
        # Therefore we choose a long timeout which is not expected uncomfortably long for operators.
        read_timeout_seconds = 30
        request_timeout = (connect_timeout_seconds, read_timeout_seconds)

        try:
            response = requests.get(gossip_url, timeout=request_timeout)
        except (ConnectionError, Timeout) as exc:
            message = (
                'Retrying GET request to {url} as error {exc} was given.'
            ).format(url=gossip_url, exc=exc)
            log.info(message)
            return False

        try:
            response.raise_for_status()
        except HTTPError as exc:
            # 150 bytes was chosen arbitrarily as it might not be so long as to
            # cause annoyance in a console, but it might be long enough to show
            # some useful data.
            first_150_bytes = response.content[:150]
            decoded_first_150_bytes = first_150_bytes.decode(
                encoding='ascii',
                errors='backslashreplace',
            )
            message = (
                'Retrying GET request to {url} as status code {status_code} was given.'
                'The first 150 bytes of the HTTP response, '
                'decoded with the ASCII character encoding: '
                '"{resp_text}".'
            ).format(
                url=gossip_url,
                status_code=response.status_code,
                resp_text=decoded_first_150_bytes,
            )
            log.info(message)
            return False

        output = json.loads(response.text)
        try:
            cluster_id_bytes = output['infos']['cluster-id']['value']['rawBytes']
        except KeyError:
            return False
        log.info((
            'Cluster ID bytes {} present in local gossip endpoint.'
        ).format(cluster_id_bytes))
        return True

    # By default cockroachdb grows the cache to 25% of available
    # memory. This makes no sense given our comparatively tiny amount
    # of data. The following limit of 100MiB was experimentally
    # determined to result in good enough performace for the IAM with
    # 60k groups, 15k users and 15 resources per group.
    #
    # This was done by populating a cockroachdb instance with the
    # aforementioend data and observing <100MiB and query performance was
    # still very fast <100ms /permissions queries.
    #
    # When cockroachdb gains more tenant services and performance is
    # found to drop, this value may be adjusted empirically.
    cachesize = '100MiB'
    cockroach_args = [
        '/opt/mesosphere/active/cockroach/bin/cockroach',
        'start',
        '--logtostderr',
        '--cache={}'.format(cachesize),
        '--store=/var/lib/dcos/cockroach',
        '--insecure',
        '--advertise-addr={}'.format(ip),
        '--listen-addr={}:26257'.format(ip),
        '--http-addr=127.0.0.1:8090',
        '--pid-file={}'.format(PID_FILE_PATH),
        '--log-dir='
    ]

    # Launch CockroachDB as the 'dcos_cockroach' user so file and directory ownership are set correctly.
    dcos_cockroach_uid = pwd.getpwnam('dcos_cockroach').pw_uid

    def run_as_dcos_cockroach() -> Any:
        """
        This function is a hack to make `os.setuid()`'s type signature match what mypy is expecting
        for preexec_fn.
        """
        os.setuid(dcos_cockroach_uid)
        return

    log.info("Initializing CockroachDB cluster: {}".format(' '.join(cockroach_args)))
    proc = subprocess.Popen(
        cockroach_args,
        preexec_fn=run_as_dcos_cockroach,
    )

    log.info("Waiting for CockroachDB to become ready.")
    _wait_for_cluster_init()
    log.info("CockroachDB cluster has been initialized.")

    # Terminate CockroachDB instance to start it via systemd unit again later.
    log.info("Terminating CockroachDB bootstrap instance.")
    # Send SIGTERM to the cockroach process to trigger a graceful shutdown.
    proc.terminate()
    # We pass no timeout and rely on systemd to stop this process after
    # `TimeoutStartSec` as specified in the unit file.
    proc.wait()
    log.info("Terminated CockroachDB bootstrap instance.")


def _get_registered_nodes(zk: KazooClient, zk_path: str) -> List[str]:
    """
    Return the IPs of nodes that have registered in ZooKeeper.

    The ZNode `zk_path` is expected to exist, having been
    created during cluster bootstrap.

    Args:
        zk:
            The client to use to communicate with ZooKeeper.
        zk_path:
            The path of the ZNode to use for node registration.

    Returns:
        A list of internal IP addresses of nodes that have
        previously joined the CockroachDB cluster.
    """
    # We call `sync()` before reading the value in order to
    # read the latest data written to ZooKeeper.
    # See https://zookeeper.apache.org/doc/r3.1.2/zookeeperProgrammers.html#ch_zkGuarantees
    log.info("Calling sync() on ZNode `{}`".format(zk_path))
    zk.sync(zk_path)
    log.info("Loading data from ZNode `{}`".format(zk_path))
    data, _ = zk.get(zk_path)
    if data:
        log.info("Cluster was previously initialized.")
        nodes = json.loads(data.decode('ascii'))['nodes']  # type: List[str]
        log.info("Found registered nodes: {}".format(nodes))
        return nodes
    log.info("Found no registered nodes.")
    return []


def _register_cluster_membership(zk: KazooClient, zk_path: str, ip: str) -> List[str]:
    """
    Add `ip` to the list of cluster members registered in ZooKeeper.

    The ZK lock must be held around the call to this function.

    Args:
        zk:
            The client to use to communicate with ZooKeeper.
        zk_path:
            The path of the ZNode to use for node registration.
        ip:
            The ip to add to the list of cluster member IPs in ZooKeeper.
    """
    log.info("Registering cluster membership for `{}`".format(ip))
    # Get the latest list of cluster members.
    nodes = _get_registered_nodes(zk=zk, zk_path=zk_path)
    if ip in nodes:
        # We're already registered with ZK.
        log.info("Cluster member `{}` already registered in ZooKeeper. Skipping.".format(ip))
        return nodes
    log.info("Adding `{}` to list of nodes `{}`".format(ip, nodes))
    nodes.append(ip)
    zk.set(zk_path, json.dumps({"nodes": nodes}).encode("ascii"))
    zk.sync(zk_path)
    log.info("Successfully registered cluster membership for `{}`".format(ip))
    return nodes


def _dump_nodes_to_file(nodes: List[str], file_path: str) -> None:
    with open(file_path, 'w') as f:
        log.info("Writing nodes {} to file {}".format(','.join(nodes), file_path))
        f.write(','.join(nodes))


def main() -> None:
    logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')

    # Determine our internal IP.
    my_ip = utils.detect_ip()
    log.info("My IP is `{}`".format(my_ip))

    # Connect to ZooKeeper.
    log.info("Connecting to ZooKeeper.")
    zk_user = os.environ.get('DATASTORE_ZK_USER')
    zk_secret = os.environ.get('DATASTORE_ZK_SECRET')
    zk = zk_connect(zk_user=zk_user, zk_secret=zk_secret)
    # We are connected to ZooKeeper.

    # Ensure that the ZNodes exist.
    zk.ensure_path("/cockroach")
    zk.ensure_path("/cockroach/nodes")
    zk.ensure_path("/cockroach/locking")

    # Determine whether the cluster has been bootstrapped already by
    # checking whether the `ZK_NODES_PATH` ZNode has children. This is
    # best-effort as we aren't holding the lock, but we do call
    # `zk.sync()` which is supposed to ensure that we read the latest
    # value from ZK.
    nodes = _get_registered_nodes(zk=zk, zk_path=ZK_NODES_PATH)
    if nodes:
        # The cluster has already been initialized. Dump the node IPs to
        # `NODES_FILE_PATH` and exit.
        log.info("Cluster has members registered already: {}".format(nodes))
        if my_ip not in nodes:
            log.info("IP not found in list of nodes. Registering cluster membership.")
            with _zk_lock(zk=zk, lock_path=ZK_LOCK_PATH, contender_id=LOCK_CONTENDER_ID, timeout=ZK_LOCK_TIMEOUT):
                nodes = _register_cluster_membership(zk=zk, zk_path=ZK_NODES_PATH, ip=my_ip)
        _dump_nodes_to_file(nodes, NODES_FILE_PATH)
        log.info("Registration complete. ")
        return

    # No cockroachdb nodes have been registered with ZK yet. We
    # assume that we need to bootstrap the cluster so we take the ZK
    # lock and hold it until the cluster is bootstrapped and our IP
    # has been successfully registered with ZK.
    #
    # The lock needs to be held around the entire cockroachdb startup
    # procedure as only the first instance should start without the
    # --join parameter (and thereby bootstrap the cluster.) This lock
    # prevents multiple instances from starting without --join at the
    # same time.
    #
    # If we fail to acquire the lock it means a peer is already
    # bootstrapping the cluster. We should crash and when we get
    # restarted by systemd, we expect to see that the cluster has been
    # bootstrapped and will enter that alternative code path which
    # leads to an eventually converged cluster.
    with _zk_lock(zk=zk, lock_path=ZK_LOCK_PATH, contender_id=LOCK_CONTENDER_ID, timeout=ZK_LOCK_TIMEOUT):
        # We check that the cluster hasn't been bootstrapped since we
        # first read the list of nodes from ZK.
        log.info("Checking for registered nodes while holding lock.")
        nodes = _get_registered_nodes(zk=zk, zk_path=ZK_NODES_PATH)
        if nodes:
            # The cluster has been bootstrapped since we checked. We join the
            # existing cluster and dump the node IPs.
            log.info("Cluster has already been initialized: {}".format(nodes))
            nodes = _register_cluster_membership(zk=zk, zk_path=ZK_NODES_PATH, ip=my_ip)
            _dump_nodes_to_file(nodes, NODES_FILE_PATH)
            return
        else:
            log.info("Cluster has not been initialized yet.")
            # The cluster still has not been bootstrapped. We start
            # cockroachdb without a list of cluster IPs to join,
            # which will cause it to bootstrap the cluster.
            _init_cockroachdb_cluster(ip=my_ip)
            # Only now that the CockroachDB cluster has been initialized, we
            # add our IP to the list of nodes that have successfully joined the
            # cluster at one stage or another.
            #
            # If this fails the fact that a cluster was initialized will be
            # ignored by subsequent runs as our IP won't be present in ZK.
            nodes = _register_cluster_membership(zk=zk, zk_path=ZK_NODES_PATH, ip=my_ip)
            _dump_nodes_to_file(nodes, NODES_FILE_PATH)
            log.info("Successfully initialized cluster.")
            return


if __name__ == '__main__':
    main()
