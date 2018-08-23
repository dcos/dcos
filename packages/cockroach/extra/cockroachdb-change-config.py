#!/usr/bin/env python
import json
import logging
import subprocess

from dcos_internal_utils import utils


"""Use this node's internal IP address to reach the local CockroachDB instance
and update its configuration state.

This program must be expected to be invoked periodicially or arbitrarily often.
That is, each configuration update must be idempotent, or at least it must be
applicable multiple times at arbitrary points in time during cluster runtime
without harming the operation of CockroachDB.
"""


log = logging.getLogger(__name__)
logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')


def set_cluster_version(my_internal_ip: str, version: str) -> None:
    """
    Use `cockroach sql` to set the cluster-wide configuration setting
    version to `version`. This requires that all nodes are running the
    given version of CockroachDB and are operating successfully.

    Relevant JIRA ticket: https://jira.mesosphere.com/browse/DCOS-19427

    Args:
        my_internal_ip: The internal IP of the current host.
        version: The current 'major.minor' version of CockroachDB.
    """
    command = [
        '/opt/mesosphere/active/cockroach/bin/cockroach',
        'sql',
        '--insecure',
        '--host={}'.format(my_internal_ip),
        '-e',
        "SET CLUSTER SETTING version = '{}';".format(version),
        ]
    config_text = 'version: {}'.format(version)
    log.info('Set `%s` via command `%s`', config_text, ' '.join(command))
    subprocess.run(command, input=config_text.encode('ascii'))
    log.info('Command returned')


def set_num_replicas(my_internal_ip: str, num_replicas: int) -> None:
    """
    Use `cockroach zone set` to set the cluster-wide configuration setting
    num_replicas to `num_replicas`. This does not matter on a 3-master
    DC/OS cluster because the CockroachDB default for num_replicas is 3.
    This however ensures that num_replicas is set to 5 on a 5-master DC/OS
    cluster. Feed the configuration key/value pair to the `cockroach` program
    via stdin.

    Relevant JIRA ticket: https://jira.mesosphere.com/browse/DCOS-20352
    """
    command = [
        '/opt/mesosphere/active/cockroach/bin/cockroach',
        'zone',
        'set',
        '.default',
        '--insecure',
        '--host={}'.format(my_internal_ip),
        '-f',
        '-'
        ]
    config_text = 'num_replicas: %s' % (num_replicas, )
    log.info('Set `%s` via command `%s`', config_text, ' '.join(command))
    subprocess.run(command, input=config_text.encode('ascii'))
    log.info('Command returned')


def get_expected_master_node_count() -> int:
    """Identify and return the expected number of DC/OS master nodes."""

    # This is the expanded DC/OS configuration JSON document w/o sensitive
    # values. Read it, parse it.
    dcos_cfg_path = '/opt/mesosphere/etc/expanded.config.json'
    with open(dcos_cfg_path, 'rb') as f:
        dcos_config = json.loads(f.read().decode('utf-8'))

    # If `master_discovery` is set to `static` then the `master_list` config key
    # is present and the reference.
    if dcos_config['master_discovery'] == 'static':
        # The `'master_list'` key holds a value which is unfortunately not
        # a list, but a stringified list. Example value:
        # '["10.10.0.131", "10.10.0.16", "10.10.0.22"]'
        log.info("Get master node count from dcos_config['master_list']")
        log.info("dcos_config['master_list']: %r", dcos_config['master_list'])
        return len(dcos_config['master_list'].split(','))

    # For dynamic master node discovery the expected number of master nodes is
    # provided by the `num_masters` config key.
    log.info("Get master node count from dcos_config['num_masters']")
    return int(dcos_config['num_masters'])


def main() -> None:
    # Determine the internal IP address of this node.
    my_internal_ip = utils.detect_ip()
    log.info('My internal IP address is `{}`'.format(my_internal_ip))

    master_node_count = get_expected_master_node_count()
    log.info('Expected number of DC/OS master nodes: %s', master_node_count)

    set_num_replicas(my_internal_ip, master_node_count)

    # We are running CockroachDB v1.1.x so pass '1.1'.
    set_cluster_version(my_internal_ip, '1.1')


if __name__ == '__main__':
    main()
