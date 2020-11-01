#!/usr/bin/env python
"""
Creates the calico docker network if it does not exist, and configures
docker with etcd as its cluster-store backend
"""

import json
import os
import shlex
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from collections import OrderedDict

from contextlib import contextmanager
from typing import Generator

import retrying

from kazoo.client import KazooClient
from kazoo.exceptions import (
    ConnectionLoss,
    LockTimeout,
    NoNodeError,
    SessionExpiredError,
)
from kazoo.retry import KazooRetry
from kazoo.security import make_digest_acl


DOCKER_BIN = "/usr/bin/docker"
DOCKERD_CONFIG_FILE = "/etc/docker/daemon.json"
DOCKER_RESTART_FILE = '/run/dcos/calico-docker-restart'
CALICO_DOCKER_NETWORK_NAME = "calico"
CLUSTER_STORE_DOCKER_INFO_PREFIX = "Cluster Store"
ETCD_ENDPOINTS_ENV_KEY = "ETCD_ENDPOINTS"
ETCD_CA_CERT_FILE_ENV_KEY = "ETCD_CA_CERT_FILE"
ETCD_CERT_FILE_ENV_KEY = "ETCD_CERT_FILE"
ETCD_KEY_FILE_ENV_KEY = "ETCD_KEY_FILE"
ETCD_CLUSTER_STORE_OPTS_ENV_KEY = "ETCD_CLUSTER_STORE_OPTS"
ZK_SERVER = "leader.mesos:2181"
ZK_PREFIX = "/cluster/boot/calico-libnetwork-plugin"


def zk_connect():
    print("Connecting to ZooKeeper")
    zk_user = os.environ.get('CALICO_ZK_USER')
    zk_secret = os.environ.get('CALICO_ZK_SECRET')
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
        hosts=ZK_SERVER,
        timeout=30,
        connection_retry=conn_retry_policy,
        command_retry=cmd_retry_policy,
        default_acl=default_acl,
        auth_data=auth_data,
    )
    zk.start()
    return zk


@contextmanager
def zk_cluster_lock(zk: KazooClient, name: str, timeout: int = 30) -> Generator:
    lock = zk.Lock("{}/{}".format(ZK_PREFIX, name), socket.gethostname())
    try:
        print("Acquiring cluster lock '{}'".format(name))
        lock.acquire(blocking=True, timeout=timeout)
    except (ConnectionLoss, SessionExpiredError) as e:
        print("Failed to acquire cluster lock: {}".format(e.__class__.__name__))
        raise e
    except LockTimeout as e:
        print("Failed to acquire cluster lock in {} seconds".format(timeout))
        raise e
    else:
        print("ZooKeeper lock acquired.")
    try:
        yield
    finally:
        print("Releasing ZooKeeper lock")
        lock.release()
        print("ZooKeeper lock released.")


def zk_flag_set(zk: KazooClient, name: str, value: str):
    path = "{}/{}".format(ZK_PREFIX, name)
    data = value.encode('utf-8')
    try:
        zk.set(path, data)
    except NoNodeError:
        zk.create(path, data, makepath=True)


def zk_flag_get(zk: KazooClient, name: str) -> str:
    path = "{}/{}".format(ZK_PREFIX, name)
    try:
        value, info = zk.get(path)
        return value.decode('utf-8')
    except NoNodeError:
        return ""
    except Exception as e:
        print("Failed to read {}: {}".format(path, e))
        raise e


def exec_cmd(cmd: str, check=False) -> subprocess.CompletedProcess:
    print("Executing: {}".format(cmd))
    process = subprocess.run(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding='utf-8',
        check=check)
    return process


def wait_calico_libnetwork_ready():
    """ wait until Calico libnetwork plugin and Calico IPAM ready

    Calico libnetwork plugin and Calico IPAM are checked according to calico
    libnetwork API call:
    https://github.com/projectcalico/libnetwork-plugin#monitoring
    """
    plugin_address = "/run/docker/plugins/calico.sock"
    plugin_check_path = "NetworkDriver.GetCapabilities"
    ipam_address = "/run/docker/plugins/calico-ipam.sock"
    ipam_check_path = "IpamDriver.GetCapabilities"

    def _check_calico_socket_server(server_address, check_path):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(server_address)
        sock.settimeout(4)
        check_request = "GET /{} HTTP/1.0\r\n\r\n".format(check_path)
        sock.send(check_request.encode())
        ret = sock.recv(1024).decode()
        return True if "HTTP/1.0 200 OK" in ret else False

    @retrying.retry(
        wait_fixed=5 * 1000,
        stop_max_delay=30 * 1000,
        retry_on_exception=lambda x: True,
        retry_on_result=lambda x: x is False)
    def _wait_calico_libnetwork_ready():
        print("Begin to check Calico libnetwork plugin and IPAM")
        plugin_check_ret = _check_calico_socket_server(plugin_address,
                                                       plugin_check_path)
        if not plugin_check_ret:
            return False
        ipadm_check_ret = _check_calico_socket_server(ipam_address,
                                                      ipam_check_path)
        if not ipadm_check_ret:
            return False
        print("Finished to check Calico libnetwork plugin and IPAM")
        return True

    return _wait_calico_libnetwork_ready()


def reload_docker_daemon():
    """
    There is no `reload` command on systemctl for Docker. However Docker will
    reload the relevant configuration when SIGHUP is sent to its process
    """
    docker_pid_file = "/var/run/docker.pid"
    if os.path.exists(docker_pid_file):
        with open(docker_pid_file, "r") as f:
            docker_pid = int(f.read())
        try:
            print("Attempting reload for docker daemon with pid={}".format(docker_pid))
            os.kill(docker_pid, signal.SIGHUP)
            return
        except OSError:
            # The pid is stale, Docker is not running. Start it now.
            traceback.print_exc(limit=1)

    print("Unable to reload daemon, restart it instead")
    # If the Docker service starts before we setup the certificates, the unit
    # may have entered failed state with an exhausted StartLimit.  Reset the
    # limits and then restart. See https://jira.d2iq.com/browse/D2IQ-72103
    exec_cmd('systemctl reset-failed docker.service')
    exec_cmd("systemctl start docker")


def is_docker_cluster_store_configured():
    docker_info_cmd = "{} info".format(DOCKER_BIN)
    p = exec_cmd(docker_info_cmd)
    docker_infos = p.stdout.strip().split('\n')
    for item in docker_infos:
        # An example of cluster store listed by `docker info`:
        # Cluster Store: etcd://master.dcos.thisdcos.directory:2379
        if item.strip().startswith(CLUSTER_STORE_DOCKER_INFO_PREFIX):
            print("Found cluster store config: {}".format(item))
            return True
    return False


def write_file_bytes(filename, data, mode):
    """
    Set the contents of file to a byte string.

    The code ensures an atomic write by creating a temporary file and then
    moving that temporary file to the given ``filename``. This prevents race
    conditions such as the file being read by another process after it is
    created but not yet written to.

    It also prevents an invalid file being created if the `write` fails (e.g.
    because of low disk space).

    The new file is created with permissions `mode`.
    """
    prefix = os.path.basename(filename)
    tmp_file_dir = os.path.dirname(os.path.realpath(filename))
    fd, temporary_filename = tempfile.mkstemp(prefix=prefix, dir=tmp_file_dir)
    # On Linux `mkstemp` initially creates file with permissions 0o600
    try:
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        os.chmod(temporary_filename, stat.S_IMODE(mode))
        os.replace(temporary_filename, filename)
    except Exception:
        os.remove(temporary_filename)
        raise


def config_docker_cluster_store():
    # load any previous daemon configuration
    if os.path.exists(DOCKERD_CONFIG_FILE):
        with open(DOCKERD_CONFIG_FILE, "rb") as f:
            try:
                existing_contents = f.read()
                # Load config with an OrderedDict to minimize changes to an existing file
                dockerd_config = json.loads(existing_contents, object_pairs_hook=OrderedDict)
                print('Checking existing Docker daemon configuration {!r}'.format(DOCKERD_CONFIG_FILE))
            except Exception as e:
                raise RuntimeError(
                    "Cannot load Docker daemon configuration {!r}: {}".format(DOCKERD_CONFIG_FILE, str(e))
                ) from e
        mode = stat.S_IMODE(os.stat(DOCKERD_CONFIG_FILE)[stat.ST_MODE])
    else:
        existing_contents = None
        dockerd_config = {}
        mode = 0o644
        print('Creating Docker daemon configuration {!r}'.format(DOCKERD_CONFIG_FILE))

    p = exec_cmd("/opt/mesosphere/bin/detect_ip", check=True)
    private_node_ip = p.stdout.strip()
    dockerd_config.update({
        "cluster-store": "etcd://master.dcos.thisdcos.directory:2379",
        "cluster-advertise": "{}:62376".format(private_node_ip),
    })

    etcd_endpoints = os.getenv(ETCD_ENDPOINTS_ENV_KEY)
    if etcd_endpoints.startswith("https"):
        print("etcd secure mode is enabled")
        # `bootstrap calico-felix` will create a JSON file containing the
        # `cluster-store-opts` configuration for secure mode.
        cluster_store_opts_path = os.getenv(ETCD_CLUSTER_STORE_OPTS_ENV_KEY)
        if not cluster_store_opts_path:
            print("Error: Environment variable {} not set", ETCD_CLUSTER_STORE_OPTS_ENV_KEY)
            sys.exit(1)
        with open(cluster_store_opts_path, 'r') as f:
            cluster_store_opts = json.load(f)
        ok = True
        for key in ('kv.cacertfile', 'kv.certfile', 'kv.keyfile'):
            val = cluster_store_opts.get(key)
            if not val:
                print("Error: {} is required for secure mode etcd", key)
                ok = False
            elif not os.path.exists(val):
                print("Error: the {} file {} does not exist", key, val)
                ok = False
        if not ok:
            sys.exit(1)
        dockerd_config["cluster-store-opts"] = cluster_store_opts
    else:
        # Remove any previously configured key options
        dockerd_config.pop("cluster-store-opts", None)

    updated_contents = json.dumps(dockerd_config, indent='\t').encode('ascii')
    if updated_contents == existing_contents:
        print('Docker daemon configuration has expected contents')
    else:
        print("Writing updated Docker daemon configuration to {!r}".format(DOCKERD_CONFIG_FILE))
        write_file_bytes(DOCKERD_CONFIG_FILE, updated_contents, mode)

    if os.path.exists(DOCKER_RESTART_FILE):
        # Force a Docker restart by stopping the daemon.  The reload code will
        # then start the daemon rather than reloading the configuration.
        exec_cmd("systemctl stop docker")
        os.unlink(DOCKER_RESTART_FILE)
    reload_docker_daemon()

    # Wait until daemon is reloaded and the configuration applied
    @retrying.retry(
        wait_fixed=5 * 1000,
        stop_max_delay=30 * 1000,
        retry_on_exception=lambda x: True,
        retry_on_result=lambda x: x is False)
    def _wait_docker_cluster_store_config():
        if not is_docker_cluster_store_configured():
            raise Exception("Cluster store not configured")
        return True

    _wait_docker_cluster_store_config()


def is_docker_calico_network_available(retries: int = 5) -> bool:
    print("Checking if '{}' docker network already exists".format(
        CALICO_DOCKER_NETWORK_NAME))
    while retries > 0:
        docker_inspect_cmd = "{} network inspect {}".format(
            DOCKER_BIN, CALICO_DOCKER_NETWORK_NAME)
        p = exec_cmd(docker_inspect_cmd, check=False)
        if p.returncode == 0:
            print("Docker network exists")
            return True

        # Make sure that's an expected error
        if 'No such network' not in p.stderr:
            raise Exception("Unexpected docker error: {}".format(p.stderr))

        # Don't immediately fail if the network does not exist, since it might
        # take a few seconds for the network information to be propagated to all
        # the docker nodes in the cluster.
        if retries > 0:
            print("Docker network not found, {} retries left".format(retries))
            retries -= 1
            time.sleep(1)

    print("Docker network does not exist")
    return False


def create_calico_docker_network():
    # Avoid race conditions by obtaining a cluster-wide exclusive lock
    # (using zookeeper) and letting only one agent execute the logic.
    zk = zk_connect()
    with zk_cluster_lock(zk, "mutex"):
        net_wait_delay = 5

        # Check if the network was (presumably) already created by another
        # agent in the cluster. If that's the case we have to increase the time
        # we wait for the docker network to appear in order to validate it.
        created_by = zk_flag_get(zk, "created_by")
        if created_by:
            net_wait_delay = 120

        # Docker takes some time to propagate the network information to all the
        # agents. Depending on the cluster size this might even take up to a
        # minute. We have to be patient and wait for the network to appear,
        # otherwise we are risking creating the same network twice.
        if is_docker_calico_network_available(net_wait_delay):
            print("Not creating docker network")
            return
        else:
            if created_by:
                raise Exception("The network should have been created by {}, "
                                "but did not appear on time".format(created_by))

        subnet = os.getenv("CALICO_IPV4POOL_CIDR")
        if not subnet:
            raise Exception(
                "Environment variable CALICO_IPV4POOL_CIDR is not set")

        net_create_cmd = "{} network create --driver calico " \
            "--opt org.projectcalico.profile={} " \
            "--ipam-driver calico-ipam --subnet={} {}".format(
                DOCKER_BIN, CALICO_DOCKER_NETWORK_NAME, subnet,
                CALICO_DOCKER_NETWORK_NAME)
        p = exec_cmd(net_create_cmd, check=False)
        if p.returncode != 0:
            # here we double-check the existence of calico network in case the
            # calico libnetwork plugin from other nodes creates it concurrently.
            if "already exists" in p.stderr:
                print("calico docker network '{}' was already installed".format(
                    CALICO_DOCKER_NETWORK_NAME))
                return
            raise Exception("Create calico network failed for {}", p.stderr)

        # Wait until docker reports the network as available
        if not is_docker_calico_network_available(5):
            raise Exception("Could not create docker network")

        print("calico docker is created, name:{}, subnet:{}".format(
            CALICO_DOCKER_NETWORK_NAME, subnet))

        # Set a flag in ZK denoting that we are the ones created the
        # calico network.
        zk_flag_set(zk, "created_by", socket.gethostname())


def main():
    wait_calico_libnetwork_ready()
    config_docker_cluster_store()
    create_calico_docker_network()


if __name__ == '__main__':
    main()
