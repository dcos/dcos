#!/usr/bin/env python
"""
This script creates the calico docker network if not exist, and configures
docker with etcd as its cluster-store backend
"""

import json
import os
import shlex
import socket
import subprocess
import sys
import time

import retrying

CALICO_DOCKER_NETWORK_NAME = "calico"
CLUSTER_STORE_DOCKER_INFO_PREFIX = "Cluster Store"
ETCD_ENDPOINTS_ENV_KEY = "ETCD_ENDPOINTS"
ETCD_CA_CERT_FILE_ENV_KEY = "ETCD_CA_CERT_FILE"
ETCD_CERT_FILE_ENV_KEY = "ETCD_CERT_FILE"
ETCD_KEY_FILE = "ETCD_KEY_FILE"


def exec_cmd(cmd: str, check=False) -> subprocess.CompletedProcess:
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


def config_docker_cluster_store():
    docker_info_cmd = "docker info"
    p = exec_cmd(docker_info_cmd)
    docker_infos = p.stdout.strip().split('\n')
    for item in docker_infos:
        # An example of cluster store listed by `docker info`:
        # Cluster Store: etcd://master.dcos.thisdcos.directory:2379
        if not item.startswith(CLUSTER_STORE_DOCKER_INFO_PREFIX):
            continue
        print("Docker cluster store has already been configured, {}".format(
            item))
        return

    # cluster-store related options can take effect by reloading docker without
    # requiring to restart docker daemon process, according to
    # https://docs.docker.com/engine/reference/commandline/dockerd/#miscellaneous-options # NOQA
    # cluster-advertise is required to make cluster-store take effect
    with open("/etc/docker/daemon.json", "w") as f:
        p = exec_cmd("/opt/mesosphere/bin/detect_ip", check=True)
        private_node_ip = p.stdout.strip()
        dockerd_config = {
            "cluster-store": "etcd://master.dcos.thisdcos.directory:2379",
            "cluster-advertise": "{}:62376".format(private_node_ip),
        }
        etcd_endpoints = os.getenv(ETCD_ENDPOINTS_ENV_KEY)
        if etcd_endpoints.startswith("https"):
            print("etcd secure mode is enabled")
            env_key_file_map = {
                ETCD_CA_CERT_FILE_ENV_KEY: os.getenv(ETCD_CA_CERT_FILE_ENV_KEY),
                ETCD_CERT_FILE_ENV_KEY: os.getenv(ETCD_CERT_FILE_ENV_KEY),
                ETCD_KEY_FILE: os.getenv(ETCD_KEY_FILE),
            }
            # all calico node components rely on felix to intialize a calico
            # node and generate etcd client secrets.
            for key, val in env_key_file_map.items():
                if not val:
                    print("Error: ENV {} is required for secure mode etcd", key)
                    sys.exit(1)
                if not os.path.exists(val):
                    print("Error: the file {} does not exist", val)
                    sys.exit(1)
            cluster_store_opts = {
                "kv.cacertfile": env_key_file_map[ETCD_CA_CERT_FILE_ENV_KEY],
                "kv.certfile": env_key_file_map[ETCD_CERT_FILE_ENV_KEY],
                "kv.keyfile": env_key_file_map[ETCD_KEY_FILE],
            }
            dockerd_config.update(
                {"cluster-store-opts": cluster_store_opts})

        # configure cluster store for secure mode etcd
        json.dump(dockerd_config, f)
    reload_docker_cmd = "systemctl reload docker"
    exec_cmd(reload_docker_cmd)


def create_calico_docker_network():
    inspect_net_cmd = "docker inspect {}".format(CALICO_DOCKER_NETWORK_NAME)
    p = exec_cmd(inspect_net_cmd, check=False)
    if p.returncode == 0:
        return

    subnet = os.getenv("CALICO_IPV4POOL_CIDR")
    if not subnet:
        raise Exception("Environment varialbe CALICO_IPV4POOL_CIDR is not set")

    net_create_cmd = "/usr/bin/docker network create --driver calico " \
        "--ipam-driver calico-ipam --subnet={} {}".format(
            subnet, CALICO_DOCKER_NETWORK_NAME)
    p = exec_cmd(net_create_cmd, check=False)
    if p.returncode != 0:
        # here we double-check the existence of calico network in case the
        # calico libnetwork plugin from other nodes creates it concurrently.
        if "network with name calico already exists" in p.stdout:
            print("calico docker network '{}' has been created".format(
                CALICO_DOCKER_NETWORK_NAME))
            return
        raise Exception("Create calico network failed for {}", p.stderr)
    print("calico docker is created, name:{}, subnet:{}".format(
        CALICO_DOCKER_NETWORK_NAME, subnet))


def main():
    wait_calico_libnetwork_ready()
    config_docker_cluster_store()
    # Before cluster-store takes effect in docker, creating calico docker
    # network will fail.
    # normally reloading docker takes less than one second, to ensure docker
    # configuration is reloaded before creating calico network, we wait a few
    # seconds first.
    time.sleep(2)
    create_calico_docker_network()


if __name__ == '__main__':
    main()
