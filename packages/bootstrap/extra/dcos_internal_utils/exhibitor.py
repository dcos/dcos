import logging
import os
import re
import socket
import sys

import requests

from dcos_internal_utils import utils

log = logging.getLogger(__name__)


EXHIBITOR_STATUS_URL = 'http://127.0.0.1:8181/exhibitor/v1/cluster/status'


_zk_mode_pat = re.compile(br'^Mode: (.*)$', re.MULTILINE)
ZK_MODE_LATENT = 'latent'
ZK_MODE_STANDALONE = 'standalone'
ZK_MODE_FOLLOWER = 'follower'
ZK_MODE_LEADER = 'leader'

zk_mode_map = {
    b'standalone': ZK_MODE_STANDALONE,
    b'follower': ZK_MODE_FOLLOWER,
    b'leader': ZK_MODE_LEADER
}


def get_zookeeper_mode():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        server_address = ('127.0.0.1', 2181)
        sock.connect(server_address)
        sock.sendall(b'srvr\n')
        response = b''
        buf = sock.recv(512)
        while buf != b'':
            response += buf
            buf = sock.recv(512)
    match = _zk_mode_pat.search(response)
    if match:
        mode = match.group(1)
        result = zk_mode_map.get(mode)
        if result is None:
            raise KeyError('Unexpected mode: {} in {}'.format(mode, response))
        return result
    if response.strip() == b'This ZooKeeper instance is not currently serving requests':
        return ZK_MODE_LATENT
    raise RuntimeError('Unexpected response: {}'.format(response))


def wait(master_count_filename):
    if not os.path.exists(master_count_filename):
        log.info("master_count file doesn't exist when it should. Hard failing.")
        sys.exit(1)

    cluster_size = int(utils.read_file_line(master_count_filename))
    log.info('Expected cluster size: {}'.format(cluster_size))

    log.info('Waiting for ZooKeeper cluster to stabilize')
    try:
        zk_mode = get_zookeeper_mode()
    except ConnectionRefusedError:
        log.error('ZooKeeper not running')
        sys.exit(1)

    if cluster_size == 1:
        desired_modes = {ZK_MODE_STANDALONE}
    else:
        desired_modes = {ZK_MODE_FOLLOWER, ZK_MODE_LEADER}
    if zk_mode not in desired_modes:
        log.error('ZooKeeper not in correct mode: %s', zk_mode)
        sys.exit(1)

    log.info('ZooKeeper OK: %s', zk_mode)

    # Check Exhibitor, but do not fail if it is shows unexpected results
    try:
        response = requests.get(EXHIBITOR_STATUS_URL)
    except requests.exceptions.ConnectionError as ex:
        log.error('Could not connect to exhibitor: {}'.format(ex))
        return
    if response.status_code != 200:
        log.error('Could not get exhibitor status: {}, Status code: {}'.format(
            EXHIBITOR_STATUS_URL, response.status_code))
        return

    data = response.json()

    serving = []
    leaders = []
    for node in data:
        if node['isLeader']:
            leaders.append(node['hostname'])
        if node['description'] == 'serving':
            serving.append(node['hostname'])

    log.info(
        "Serving hosts: `%s`, leader: `%s`", ','.join(serving), ','.join(leaders))

    if utils.is_static_cluster():
        # For static clusters, wait for a ZooKeeper quorum to be ready.
        quorum = cluster_size // 2 + 1
        if len(leaders) != 1 or len(serving) < quorum:
            msg_fmt = 'Require {}+ servers and 1 leader, have {} servers and {} leaders'
            log.error(msg_fmt.format(quorum, len(serving), len(leaders)))
            return
    else:
        # For other clusters, wait for all ZooKeeper nodes to be ready.
        if len(leaders) != 1 or len(serving) != cluster_size:
            msg_fmt = 'Require {} servers and 1 leader, have {} servers and {} leaders'
            log.error(msg_fmt.format(cluster_size, len(serving), len(leaders)))
            return

    log.info('Exhibitor OK')
