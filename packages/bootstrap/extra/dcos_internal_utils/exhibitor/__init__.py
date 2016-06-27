import logging
import os
import sys

import requests

from .. import utils

log = logging.getLogger(__name__)


EXHIBITOR_STATUS_URL = 'http://127.0.0.1:8181/exhibitor/v1/cluster/status'


def wait(master_count_filename):
    if not os.path.exists(master_count_filename):
        log.info("master_count file doesn't exist, not waiting")
        return

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

    serving = 0
    leaders = 0
    for node in data:
        if node['isLeader']:
            leaders += 1
        if node['description'] == 'serving':
            serving += 1

    if serving != cluster_size or leaders != 1:
        msg = 'Expected {} servers and 1 leader, got {} servers and {} leaders'.format(cluster_size, serving, leaders)
        raise Exception(msg)
