import logging
import os
import sys

import requests

from dcos_internal_utils import utils
from pkgpanda.util import load_string, write_string

log = logging.getLogger(__name__)


EXHIBITOR_STATUS_URL = 'http://127.0.0.1:8181/exhibitor/v1/cluster/status'

zk_pid_path = "/var/lib/dcos/exhibitor/zk.pid"
stash_zk_pid_stat_mtime_path = "/var/lib/dcos/bootstrap/exhibitor_pid_stat"


def get_zk_pid_mtime():
    try:
        return os.stat(zk_pid_path).st_mtime_ns
    except FileNotFoundError:
        log.error("ZK pid file `%s` does not exist.", zk_pid_path)
        return None


def get_zk_pid():
    return load_string(zk_pid_path)


def try_shortcut():
    try:
        # pid stat file exists, read the value out of it
        stashed_pid_stat = int(load_string(stash_zk_pid_stat_mtime_path))
    except FileNotFoundError:
        log.info('No zk.pid last mtime found at %s', stash_zk_pid_stat_mtime_path)
        return False

    # Make sure that the pid hasn't been written anew
    cur_pid_stat = get_zk_pid_mtime()

    if cur_pid_stat is None:
        return False

    if stashed_pid_stat != cur_pid_stat:
        return False

    # Check that the PID has a zk running at it currently.
    zk_pid = get_zk_pid()
    cmdline_path = '/proc/{}/cmdline'.format(zk_pid)
    try:
        # Custom because the command line is ascii with `\x00` as separator.
        with open(cmdline_path, 'rb') as f:
            cmd_line = f.read().split(b'\x00')[:-1]
    except FileNotFoundError:
        log.info('Process no longer running (couldn\'t read the cmdline at: %s)', zk_pid)
        return False

    log.info('PID %s has command line %s', zk_pid, cmd_line)

    if len(cmd_line) < 3:
        log.info("Command line too short to be zookeeper started by exhibitor")
        return False

    if cmd_line[-1] != b'/var/lib/dcos/exhibitor/conf/zoo.cfg' \
            or cmd_line[0] != b'/opt/mesosphere/active/java/usr/java/bin/java':
        log.info("command line doesn't start with java and end with zookeeper.cfg")
        return False

    log.info("PID file hasn't been modified. ZK still seems to be at that PID.")
    return True


def wait(master_count_filename):
    if try_shortcut():
        log.info("Shortcut succeeeded, assuming local zk is in good config state, not waiting for quorum.")
        return
    log.info('Shortcut failed, waiting for exhibitor to bring up zookeeper and stabilize')

    if not os.path.exists(master_count_filename):
        log.info("master_count file doesn't exist when it should. Hard failing.")
        sys.exit(1)

    cluster_size = int(utils.read_file_line(master_count_filename))
    log.info('Expected cluster size: {}'.format(cluster_size))

    log.info('Waiting for ZooKeeper cluster to stabilize')
    try:
        response = requests.get(EXHIBITOR_STATUS_URL)
    except requests.exceptions.ConnectionError as ex:
        log.error('Could not connect to exhibitor: {}'.format(ex))
        sys.exit(1)
    if response.status_code != 200:
        log.error('Could not get exhibitor status: {}, Status code: {}'.format(
            EXHIBITOR_STATUS_URL, response.status_code))
        sys.exit(1)

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
            sys.exit(1)
    else:
        # For other clusters, wait for all ZooKeeper nodes to be ready.
        if len(leaders) != 1 or len(serving) != cluster_size:
            msg_fmt = 'Require {} servers and 1 leader, have {} servers and {} leaders'
            log.error(msg_fmt.format(cluster_size, len(serving), len(leaders)))
            sys.exit(1)

    # Local Zookeeper is up. Config should be stable, local zookeeper happy. Stash the PID so if
    # there is a restart we can come up quickly without requiring a new zookeeper quorum.
    zk_pid_mtime = get_zk_pid_mtime()
    if zk_pid_mtime is not None:
        log.info('Stashing zk.pid mtime %s to %s', zk_pid_mtime, stash_zk_pid_stat_mtime_path)
        write_string(stash_zk_pid_stat_mtime_path, str(zk_pid_mtime))
