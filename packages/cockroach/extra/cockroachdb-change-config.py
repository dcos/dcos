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


def set_num_replicas(my_internal_ip: str, num_replicas: int) -> None:
    """
    CockroachDB version 2.1.7 sets the internal system range replication
    factor to `5` by default:
    https://www.cockroachlabs.com/docs/stable/configure-replication-zones.html#view-all-replication-zones

    In order to adjust this to the maximum replication factor possible for a
    given DC/OS cluster and to provide maximum fault-tolerance we set the
    cluster-wide configuration setting `num_replicas` for any database entity
    to the given `num_replicas` count which equals the number of DC/OS master
    nodes.
    Relevant JIRA ticket: https://jira.mesosphere.com/browse/DCOS-20352
    """
    zone_config = 'num_replicas = {}'.format(num_replicas)

    # If more entities that must have their `num_replicas` setting adjusted are
    # added to CockroachDB, a DC/OS check will fail on all clusters (DC/OS OSS
    # 1.13+, DC/OS Enterprise 1.12+).
    # describing that there are "underreplicated ranges".
    # The DC/OS check is named "cockroachdb_replication".
    #
    # To resolve this, add more items to the following list.
    # To display CockroachDB entities that must have their `num_replicas` setting
    # adjusted, issue the following SQL command: `SHOW ALL ZONE CONFIGURATIONS;`
    #
    # One option is to parse the output of the above SQL command.
    # However, there is a plan for CockroachDB that all replication will be
    # derived from ``.default``.
    # See https://forum.cockroachlabs.com/t/change-replication-factor/2052/3.
    # Should this happen, we can replace the following loop initialisation with:
    # zone = '.default'
    # db_entity = 'RANGE default'
    for zone, db_entity in [
        ('.default', 'RANGE default'),
        ('system', 'DATABASE system'),
        ('system.jobs', 'TABLE system.public.jobs'),
        ('.meta', 'RANGE meta'),
        ('.system', 'RANGE system'),
        ('.liveness', 'RANGE liveness'),
    ]:
        sql_command = (
            'ALTER {db_entity} CONFIGURE ZONE USING {zone_config};'
        ).format(
            db_entity=db_entity,
            zone_config=zone_config,
        )
        command = (
            '/opt/mesosphere/active/cockroach/bin/cockroach '
            'sql -e "{sql_command}" --insecure --host={host}'
        ).format(
            sql_command=sql_command,
            host=my_internal_ip,
        )
        message = (
            'Set `{zone_config}` for `{zone}` via command `{command}`'
        ).format(
            zone_config=repr(zone_config),
            zone=repr(zone),
            command=repr(command),
        )
        log.info(message)
        subprocess.run(command, shell=True)
        log.info('Command returned')


def get_expected_master_node_count() -> int:
    """Identify and return the expected number of DC/OS master nodes."""

    # This is the expanded DC/OS configuration JSON document w/o sensitive
    # values. Read it, parse it.
    dcos_cfg_path = '/opt/mesosphere/etc/expanded.config.json'
    with open(dcos_cfg_path, 'rb') as f:
        dcos_config = json.loads(f.read().decode('utf-8'))

    # If the master discovery strategy is dynamic, the num_masters
    # configuration item is required to specify the expected number of masters.
    # If the master discovery strategy is static, the num_masters configuration
    # item is auto-populated from the given master_list. As such, we rely on
    # num_masters regardless of master discovery strategy.
    log.info("Get master node count from dcos_config['num_masters']")
    return int(dcos_config['num_masters'])


def main() -> None:
    # Determine the internal IP address of this node.
    my_internal_ip = utils.detect_ip()
    log.info('My internal IP address is `{}`'.format(my_internal_ip))

    master_node_count = get_expected_master_node_count()
    log.info('Expected number of DC/OS master nodes: %s', master_node_count)

    set_num_replicas(my_internal_ip, master_node_count)


if __name__ == '__main__':
    main()
