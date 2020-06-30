#!/usr/bin/env python

import argparse
import ipaddress
import json
import logging
import os
import random
import socket
import subprocess
import sys
from contextlib import contextmanager
from typing import Dict, Generator, List, Optional, Union

from kazoo.client import KazooClient
from kazoo.exceptions import ConnectionLoss, LockTimeout, SessionExpiredError
from kazoo.retry import KazooRetry
from kazoo.security import make_digest_acl

log = logging.getLogger(__name__)

JsonTypeMembers = List[Dict[str, Union[str, int, List[str]]]]

# The path of the ZNode used for locking.
ZK_LOCK_PATH = "/etcd/locking"
# The path of the ZNode containing the list of cluster members.
ZK_NODES_PATH = "/etcd/nodes"
# The id to use when contending for the ZK lock.
LOCK_CONTENDER_ID = "{}:{}".format(socket.gethostname(), os.getpid())
# The time in seconds to wait when attempting to acquire a lock.  Lock
# acquisition between 5 ZooKeeper nodes is an operation on the order of
# milliseconds.
#
# Furthermore, the operations performed while the lock is held are performed
# once and never again. This means a process will only contend for the lock
# once. As such, if lock aquisition fails due to some other process holding it,
# the current process will crash and be restarted with one less contender for
# the same lock. This means that the locking behaviour does converge and no
# timeout-sensitive livelock can occur.
#
# We set the lock timeout to a couple of seconds instead of milliseconds to
# account for variation in network latency between nodes in the cluster. The
# current value has so far shown to be sufficient.
ZK_LOCK_TIMEOUT = 5
# Location of the detect IP address detection script
DETECT_IP_SCRIPT = '/opt/mesosphere/bin/detect_ip'


# In theory we could use the dcos_internal_utils.utils library, but in practice
# the amount of deps it pulls in is huge compared to just a simple `execute
# script and verify the output` function that we want
def detect_ip() -> str:
    machine_ip = subprocess.check_output(
        [DETECT_IP_SCRIPT],
        stderr=subprocess.STDOUT).decode('ascii').strip()  # type: str
    # Validate IP address
    ipaddress.ip_address(machine_ip)
    log.info("private IP is `%s`", machine_ip)
    return machine_ip


def zk_connect(zk_addr: str,
               zk_user: Optional[str] = None,
               zk_secret: Optional[str] = None) -> KazooClient:
    """Connect to ZooKeeper.

    On connection failure, the function attempts to reconnect indefinitely with
    exponential backoff up to 3 seconds. If a command fails, that command is
    retried every 300ms for 3 attempts before failing.

    These values are chosen to suit a human-interactive time.

    Args:
        zk_addr: The address to connect to
        zk_user: The username to use when connecting to ZooKeeper or `None`
            if no authentication is necessary.
        zk_secret: The secret to use when connecting to ZooKeeper or `None`
            if no authentication is necessary.

    Returns:
        A ZooKeeper client connection in the form of a `kazoo.client.KazooClient`.
    """
    # Try to reconnect indefinitely, with time between updates going
    # exponentially to ~3s. Then every retry occurs every ~3 seconds.
    conn_retry_policy = KazooRetry(
        max_tries=-1,
        delay=0.3,
        backoff=1.3,
        max_delay=3,
        ignore_expire=True,
    )

    # Retry commands every 0.3 seconds, for a total of <1s (usually 0.9)
    cmd_retry_policy = KazooRetry(
        max_tries=3,
        delay=0.3,
        backoff=1,
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
        hosts=zk_addr,
        timeout=30,
        connection_retry=conn_retry_policy,
        command_retry=cmd_retry_policy,
        default_acl=default_acl,
        auth_data=auth_data,
    )

    zk.start()
    return zk


@contextmanager
def zk_lock(zk: KazooClient, lock_path: str, contender_id: str,
            timeout: int) -> Generator:
    """
    This contextmanager takes a ZooKeeper lock, yields, then releases the lock.
    This lock behaves like an interprocess mutex lock.

    ZooKeeper allows one to read values without holding a lock, but there is no
    guarantee that you will read the latest value. To read the latest value,
    you must call `sync()` on a ZNode before calling `get()`.

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
        lock.acquire(blocking=True, timeout=timeout, ephemeral=True)
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
    try:
        yield
    finally:
        log.info("Releasing ZooKeeper lock")
        lock.release()
        log.info("ZooKeeper lock released.")


def get_registered_nodes(zk: KazooClient, zk_path: str) -> List[str]:
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
        previously joined the etcd cluster.
    """
    # We call `sync()` before reading the value in order to read the latest
    # data written to ZooKeeper.
    # See https://zookeeper.apache.org/doc/r3.1.2/zookeeperProgrammers.html#ch_zkGuarantees
    log.info("Calling sync() on ZNode `%s`", zk_path)
    zk.sync(zk_path)
    log.info("Loading data from ZNode `%s`", zk_path)
    data, _ = zk.get(zk_path)
    if data:
        nodes = json.loads(data.decode('ascii'))['nodes']  # type: List[str]
        log.info("Found registered nodes: %s", nodes)
        return nodes
    log.info("Found no registered nodes.")
    return []


def register_cluster_membership(zk: KazooClient, zk_path: str,
                                ip: str) -> List[str]:
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
    log.info("Registering cluster membership for `%s`", ip)
    # Get the latest list of cluster members.
    nodes = get_registered_nodes(zk=zk, zk_path=zk_path)
    if ip in nodes:
        # We're already registered with ZK.
        log.info(
            "Cluster member `%s` already registered in ZooKeeper. Skipping.",
            ip)
        return nodes
    log.info("Adding `%s` to list of nodes `%s`", ip, nodes)
    nodes.append(ip)
    zk.set(zk_path, json.dumps({"nodes": nodes}).encode("ascii"))
    zk.sync(zk_path)
    log.info("Successfully registered cluster membership for `%s`", ip)
    return nodes


def remove_cluster_membership(zk: KazooClient, zk_path: str,
                              ip: str) -> List[str]:
    """
    Remove `ip` from the list of cluster members registered in ZooKeeper.

    The ZK lock must be held around the call to this function.

    Args:
        zk:
            The client to use to communicate with ZooKeeper.
        zk_path:
            The path of the ZNode to use for node registration.
        ip:
            The ip to add to the list of cluster member IPs in ZooKeeper.
    """
    log.info("Removing cluster membership for `%s`", ip)
    # Get the latest list of cluster members.
    nodes = get_registered_nodes(zk=zk, zk_path=zk_path)
    if ip not in nodes:
        # We're already registered with ZK.
        log.info(
            "Cluster member `%s` already removed from Zookeeper. Skipping.",
            ip)
        return nodes
    log.info("Removing `%s` to list of nodes `%s`", ip, nodes)
    nodes.remove(ip)
    zk.set(zk_path, json.dumps({"nodes": nodes}).encode("ascii"))
    zk.sync(zk_path)
    log.info("Successfully removed %s from the cluster", ip)
    return nodes


def dump_nodes_to_file(nodes: List[str], file_path: str) -> None:
    log.info("Writing nodes %s to file %s", ','.join(nodes), file_path)
    with open(file_path, 'w') as f:
        nodes_str = ','.join(
            ["etcd-{ip}=https://{ip}:2380".format(ip=ip) for ip in nodes])
        f.write(nodes_str)


def dump_state_to_file(state: str, file_path: str) -> None:
    log.info("Writing initial cluster state: `%s`to file `%s`", state,
             file_path)
    with open(file_path, 'w') as f:
        f.write(state)


def parse_cmdline() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='DC/OS etcd node discovery')
    parser.add_argument(
        '--secure',
        action='store_true',
        help='enable ensure connection for etcd peers and clients.')
    parser.add_argument('--zk-addr',
                        action='store',
                        default='127.0.0.1:2181',
                        help='address of the ZK instance to connect to')
    parser.add_argument('--etcd-client-tls-cert',
                        action='store',
                        default='',
                        help='key used for connecting to etcd via etcdctl')
    parser.add_argument(
        '--etcd-client-tls-key',
        action='store',
        default='',
        help='certificate used for connecting to etcd via etcdctl')
    parser.add_argument('--etcdctl-path',
                        action='store',
                        default='/opt/mesosphere/active/etcd/bin/etcdctl',
                        help='path to etcdctl binary')
    parser.add_argument('--ca-cert',
                        action='store',
                        default='',
                        help='path to the CA certificate')
    subparsers = parser.add_subparsers(title='Subcommands', dest='subcommand')

    parser_joincluster = subparsers.add_parser('join-cluster')
    parser_joincluster.set_defaults(func=join_cluster)
    parser_joincluster.add_argument(
        '--cluster-nodes-file',
        action='store',
        default='/var/lib/dcos/etcd/initial-nodes',
        help='file where initial cluster nodes should be saved')
    parser_joincluster.add_argument(
        '--cluster-state-file',
        action='store',
        default='/var/lib/dcos/etcd/initial-state',
        help='file where initial cluster state should be saved')
    parser_joincluster.add_argument('--etcd-data-dir',
                                    action='store',
                                    default='/var/lib/dcos/etcd/default.etcd/',
                                    help="etcd's data directory location")

    parser_leavecluster = subparsers.add_parser('leave-cluster')
    parser_leavecluster.set_defaults(func=leave_cluster)
    # We want to make it overridable
    parser_leavecluster.add_argument(
        '--node-ip',
        action='store',
        default=detect_ip(),
        help="the IP address of the node to remove from the ensemble")

    parser_ensure_perms = subparsers.add_parser('ensure-permissions')
    parser_ensure_perms.set_defaults(func=ensure_permissions)

    return parser.parse_args()


def ensure_permissions(args: argparse.Namespace) -> None:
    log.info("ensure-permissions subcommand starts, args: `%s`", args)

    etcdctl = EtcdctlHelper(
        args.secure,
        # NOTE(prozlach): we intentionally do not read back the nodes list from
        # disk and connect to the local etcd instance. With more than one node
        # in a quorum we would have sometimes intra-node and sometimes inter-node
        # communication which may result in disruptions that happen only
        # sometimes and are hard to reproduce.
        [
            "127.0.0.1",
        ],
        args.etcdctl_path,
        args.ca_cert,
        args.etcd_client_tls_cert,
        args.etcd_client_tls_key,
    )

    # See below for more context:
    # https://github.com/etcd-io/etcd/blob/3898452b5432b4d69028ee79d796ddeab0acc42c/Documentation/op-guide/authentication.md
    etcdctl.ensure_user("root")
    etcdctl.grant_role("root", "root")

    etcdctl.ensure_user("calico")
    # See below for more details:
    # https://docs.projectcalico.org/v3.11/reference/etcd-rbac/calico-etcdv3-paths#calicoctl-read-only-access
    etcdctl.ensure_role("calico_prefix", "/calico/")
    etcdctl.grant_role("calico", "calico_prefix")

    etcdctl.ensure_user("adminrouter")
    etcdctl.ensure_role("adminrouter_prefix", "/")
    etcdctl.grant_role("adminrouter", "adminrouter_prefix")

    etcdctl.ensure_user("telegraf")
    etcdctl.ensure_role("telegraf_prefix", "/")
    etcdctl.grant_role("telegraf", "telegraf_prefix")

    etcdctl.enable_auth()


def join_cluster(args: argparse.Namespace) -> None:
    log.info("join-cluster subcommand starts, args: `%s`", args)

    # Check if etcd is up and running already. If so - we can skip quering ZK,
    # as etcd is able to get the list of peers directly from the shared
    # storage.
    if os.path.isdir(args.etcd_data_dir) and os.path.exists(
            args.cluster_nodes_file) and os.path.exists(args.cluster_state_file):
        log.info(
            "directory `%s`, initial nodes file `%s` and state file `%s` already exists, etcd seems initialized",
            args.etcd_data_dir, args.cluster_nodes_file, args.cluster_state_file)
        return

    # Determine our internal IP.
    private_ip = detect_ip()

    # Connect to ZooKeeper.
    log.info("connecting to ZooKeeper")
    zk_user = os.environ.get('DATASTORE_ZK_USER')
    zk_secret = os.environ.get('DATASTORE_ZK_SECRET')
    zk = zk_connect(zk_addr=args.zk_addr, zk_user=zk_user, zk_secret=zk_secret)

    nodes = []  # type: List[str]

    with zk_lock(
            zk=zk,
            lock_path=ZK_LOCK_PATH,
            contender_id=LOCK_CONTENDER_ID,
            timeout=ZK_LOCK_TIMEOUT,
    ):

        nodes = get_registered_nodes(zk=zk, zk_path=ZK_NODES_PATH)
        cluster_state = ""

        # The order of nodes is important - the first node to register
        # becomes the `designated node` that will initialize cluster, all
        # the other nodes will join it.
        # FIXME(prozlach): It's not 100% bulletproof, because if during the
        # init something happens to the first node, the whole cluster will
        # not be able to bootstrap itself. OTOH this simplifies this
        # script, as there is no need for monitoring the process from
        # within this script/making it a wrapper around etcd.
        if len(nodes) == 0:
            log.info("Cluster has not been initialized yet: %s", nodes)
            cluster_state = "new"
        else:
            # There is already at least one etcd node which we should join
            log.info("Cluster has members that already registered: %s", nodes)
            cluster_state = "existing"

            etcdctl = EtcdctlHelper(
                args.secure,
                nodes,
                args.etcdctl_path,
                args.ca_cert,
                args.etcd_client_tls_cert,
                args.etcd_client_tls_key,
            )
            if private_ip not in nodes:
                # The problem here is that once we add given etcd to the
                # quorum (e.g. the first node that started), and the said node
                # gets restarted, then etcd will not be able to start at all,
                # as we will be missing quorum. The solution is to first
                # register the node in the quorum and only then update ZK while
                # still holding the ZK lock (and thus holding back the other
                # nodes). The result is that the list of nodes in ZK reflect
                # the nodes that have been **actually** added to the quorum -
                # i.e. the `etcdctl` command was succesful. This way, once a
                # node/nodes get restarted, the quorum-member nodes will start
                # and will not try to execute etcdctl (which's failure woudl
                # block starting and creating the quorum in the first place),
                # and the non-member nodes will wait for the quorum to form (as
                # their etcdctl commands will fail and thus prevent them from
                # registering in ZK node list). It is also important to note
                # that there is a small drawback to this approach - if etcdctl
                # succeds but subsequent call ZK fail then the given node (and
                # maybe even the cluster) will not be able to start. This would
                # require ZK failing withing narrow time window though
                # (i.e. between the `get_registered_nodes` call above and
                # `register_cluster_membership` below). I belive the risk is
                # acceptable considering the simplicity of this script.
                log.info("current node is not a member of the quorum, joining "
                         "the existing quorum")
                etcdctl.ensure_member(private_ip)

            # NOTE(mainred): considering the case private IP presents in zk,
            # but dcos-etcd service hasn't run on this node ever, like master
            # node replacement.
            # we should remove the member first before joining the cluster
            # again for keeping the member without the original data will bring
            # raft exception as follows:
            #
            # tocommit(8) is out of range [lastIndex(0)]. Was the raft log corrupted, truncated, or lost? # NOQA
            elif not os.path.exists(args.etcd_data_dir):
                log.info("rejoining the quorum as a result of data loss")
                etcdctl.remove_member(private_ip)
                etcdctl.ensure_member(private_ip)

        nodes = register_cluster_membership(zk=zk,
                                            zk_path=ZK_NODES_PATH,
                                            ip=private_ip)

        # NOTE(icharala): Ensure that both node & state files are always present
        # otherwise the `etcd.sh` script will fail to start.
        dump_nodes_to_file(nodes, args.cluster_nodes_file)
        dump_state_to_file(cluster_state, args.cluster_state_file)

    log.info("registration complete")


class EtcdctlHelper:
    def __init__(
            self,
            secure: bool,
            nodes: List[str],
            etcdctl_path: str,
            ca_cert: str,
            etcd_client_tls_cert: str,
            etcd_client_tls_key: str,
    ):

        self.scheme = "https" if secure else "http"
        self._ca_cert = ca_cert
        self._etcdctl_path = etcdctl_path
        self._etcd_client_tls_cert = etcd_client_tls_cert
        self._etcd_client_tls_key = etcd_client_tls_key
        self._designated_node = None
        self._nodes = nodes

    def get_designated_node(self) -> str:
        """
        Lazily finds out the designated node to use
        """
        if self._designated_node is None:
            # Choose one node from the list
            healthy_nodes = list(filter(self._is_node_healthy, self._nodes))
            # In order to not to always hit the same node, we randomize the choice:
            if len(healthy_nodes) == 0:
                raise Exception("there are no healthy nodes")
            self._designated_node = random.choice(healthy_nodes)
        return self._designated_node

    def get_members(self) -> JsonTypeMembers:
        """ gets etcd cluster members

        an example of results of `member list -w json`
        [
          {
            'ID': 2080818695399562020,
            'name': 'etcd-10.0.4.116',
            'peerURLs': [
              'https://10.0.4.116:2380'
            ],
            'clientURLs': [
              'https://10.0.4.116:2379',
              'https://localhost:2379'
            ]
          }
        ]
        """
        result = self._execute_etcdctl(
            self.get_designated_node(),
            ["member", "list", "-w", "json"],
        )
        result.check_returncode()
        output = json.loads(result.stdout)
        members = output["members"]  # type: JsonTypeMembers

        return members

    def get_node_id(self, node_ip: str) -> str:
        """ Returns etcd member ID in Hex
        """
        members_info = self.get_members()
        for member in members_info:
            # Uninitialized members do not have "name" entry
            if "name" in member and member["name"] == "etcd-{}".format(
                    node_ip):
                assert isinstance(member["ID"], int)
                # valid member ID should be in Hex, as etcdctl will try to
                # parse the string of member ID to Hex when used
                return hex(member["ID"]).replace("0x", "")

        return ""

    def ensure_member(self, node_ip: str) -> None:
        members_info = self.get_members()
        for member in members_info:
            if "name" in member and member["name"] == "etcd-{}".format(
                    node_ip):
                log.info("node %s is already member of the ensemble", node_ip)
                return

        self.add_member(node_ip)

    def add_member(self, node_ip: str) -> None:
        result = self._execute_etcdctl(
            self.get_designated_node(),
            [
                "member",
                "add",
                "etcd-{}".format(node_ip),
                "--peer-urls=https://{}:2380".format(node_ip),
            ],
        )
        result.check_returncode()
        log.info("node %s was added to the ensemble", node_ip)

    def ensure_role(self, role_name: str, prefix: str) -> None:
        roles = self.list_roles()
        if role_name not in roles:
            self.add_role(role_name)
        self.add_permission(role_name, prefix)

    def list_roles(self) -> List[str]:
        result = self._execute_etcdctl(
            self.get_designated_node(),
            [
                "role",
                "list",
            ],
        )
        result.check_returncode()
        roles = result.stdout.decode('utf8').splitlines()  # type: List[str]
        log.info("roles currently defined: %s", roles)
        return roles

    def grant_role(self, user_name: str, role_name: str) -> None:
        result = self._execute_etcdctl(
            self.get_designated_node(),
            [
                "user",
                "grant-role",
                user_name,
                role_name,
            ],
        )
        result.check_returncode()
        log.info("role %s was granted to %s", role_name, user_name)

    def enable_auth(self) -> None:
        result = self._execute_etcdctl(
            self.get_designated_node(),
            [
                "auth",
                "enable",
            ],
        )
        result.check_returncode()
        log.info("authentication was enabled")

    def add_role(self, role_name: str) -> None:
        result = self._execute_etcdctl(
            self.get_designated_node(),
            [
                "role",
                "add",
                role_name,
            ],
        )
        result.check_returncode()
        log.info("role %s was added", role_name)

    def add_permission(self, role_name: str, prefix: str) -> None:
        result = self._execute_etcdctl(
            self.get_designated_node(),
            [
                "role",
                "grant",
                role_name,
                "--prefix=true",
                "readwrite",
                prefix,
            ],
        )
        result.check_returncode()
        log.info("prefix %s has been granted to the role %s", prefix,
                 role_name)

    def ensure_user(self, user_name: str) -> None:
        users = self.list_users()
        if user_name not in users:
            self.add_user(user_name)

    def add_user(self, user_name: str) -> None:
        result = self._execute_etcdctl(
            self.get_designated_node(),
            [
                "user",
                "add",
                "--no-password",
                user_name,
            ],
        )
        result.check_returncode()
        log.info("user %s was added", user_name)

    def list_users(self) -> List[str]:
        result = self._execute_etcdctl(
            self.get_designated_node(),
            [
                "user",
                "list",
            ],
        )
        result.check_returncode()
        users = result.stdout.decode('utf8').splitlines()  # type: List[str]
        log.info("users currently defined: %s", users)
        return users

    def remove_member(self, node_ip: str) -> None:
        node_id = self.get_node_id(node_ip)
        if node_id == "":
            log.warning("node %s is not a member yet so it cannot be removed",
                        node_ip)
            return

        result = self._execute_etcdctl(
            self.get_designated_node(),
            ["member", "remove", node_id],
        )
        result.check_returncode()
        log.info("node %s was removed from the ensemble", node_ip)

    def _is_node_healthy(self, node: str) -> bool:
        result = self._execute_etcdctl(node, ["endpoint", "health"])
        healthy = result.returncode == 0
        return healthy

    def _execute_etcdctl(self, endpoint_ip: str,
                         args: List[str]) -> subprocess.CompletedProcess:

        cmd = [
            self._etcdctl_path, "--endpoints",
            "{}://{}:2379".format(self.scheme, endpoint_ip)
        ]

        if self.scheme == "https":
            cmd.extend([
                "--cacert", self._ca_cert, "--cert",
                self._etcd_client_tls_cert, "--key", self._etcd_client_tls_key
            ])

        cmd.extend(args)
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        log.debug(
            "executed `%s`, exit status: `%d`, stdout: `%s`, stderr: `%s`",
            " ".join(cmd),
            result.returncode,
            result.stdout,
            result.stderr,
        )

        return result


def leave_cluster(args: argparse.Namespace) -> None:
    log.info("leave-cluster subcommand starts, args: `%s`", args)

    # Connect to ZooKeeper.
    log.info("connecting to ZooKeeper")
    zk_user = os.environ.get('DATASTORE_ZK_USER')
    zk_secret = os.environ.get('DATASTORE_ZK_SECRET')
    zk = zk_connect(zk_addr=args.zk_addr, zk_user=zk_user, zk_secret=zk_secret)

    with zk_lock(
            zk=zk,
            lock_path=ZK_LOCK_PATH,
            contender_id=LOCK_CONTENDER_ID,
            timeout=ZK_LOCK_TIMEOUT,
    ):
        remove_cluster_membership(zk=zk,
                                  zk_path=ZK_NODES_PATH,
                                  ip=args.node_ip)

        nodes = get_registered_nodes(zk=zk, zk_path=ZK_NODES_PATH)

        if nodes:
            # There is already at least one etcd node which we should join
            log.info("Cluster has members that already registered: %s", nodes)

        etcdctl = EtcdctlHelper(
            args.secure,
            nodes,
            args.etcdctl_path,
            args.ca_cert,
            args.etcd_client_tls_cert,
            args.etcd_client_tls_key,
        )
        etcdctl.remove_member(args.node_ip)

    log.info("removal complete")


def main() -> None:
    logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')

    args = parse_cmdline()

    try:
        args.func(args)
    except Exception as e:  # pylint: disable=broad-except
        log.exception("error occured: %s", e)
        sys.exit(1)


if __name__ == '__main__':
    main()
