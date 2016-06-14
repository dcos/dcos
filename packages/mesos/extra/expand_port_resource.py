#!/opt/mesosphere/bin/python3

import json
import os
import sys

from itertools import chain
from datetime import datetime

PROG = os.path.basename(__file__)

IDEAL_PORTS = chain(range(1, 22), range(23, 5051), range(5052, 32001))
FILE_MSG = 'Creating updated environment artifact file : {}'
RESOURCE_MSG = 'Writing new resources: {}'

RESOURCES_TEMPLATE_HEADER = '''# Generated by {prog} on {dt}
#
'''

RESOURCES_TEMPLATE = '''
MESOS_RESOURCES='{res}'
'''


def range_to_iterable(rng):
    ranges = [range(x['begin'], x['end']) for x in rng]
    return chain(*ranges)


def iterable_to_range(iterable):
    if len(iterable) == 0:
        return []
    range_iter = iter(iterable)
    first = range_iter.__next__()
    ranges = [{'begin': first, 'end': first}]
    for i in range_iter:
        if i == ranges[-1]['end'] + 1:
            ranges[-1]['end'] = i
        else:
            ranges.append({'begin': i, 'end': i})
    return ranges


def maybe_augment_resource(resource):
    if resource['name'] != 'ports':
        return resource
    port_set = frozenset(range_to_iterable(resource['ranges']['range']))
    additional_ports = frozenset(IDEAL_PORTS)
    all_ports = frozenset.union(port_set, additional_ports)
    new_range = iterable_to_range(all_ports)
    resource['ranges']['range'] = new_range
    return resource


def main(output_env_file):
    # First check if we should upgrade the resource
    # we only do this iif the agent has never checkpointed before
    checkpoint_path = os.path.join(os.environ['MESOS_WORK_DIR'], 'meta/slaves/latest')

    tmp_file = '{}.tmp'.format(output_env_file)

    env_resources = os.environ.get('MESOS_RESOURCES', '[]')

    try:
        resources = json.loads(env_resources)
    except ValueError as e:
        print('ERROR: Invalid MESOS_RESOURCES JSON {} --- {}'.format(e, env_resources), file=sys.stderr)
        sys.exit(1)

    # mode 'w' truncates the file if it exists so no need to truncate it
    with open(tmp_file, 'w') as env_file:
        env_file.write(RESOURCES_TEMPLATE_HEADER.format(prog=PROG, dt=datetime.now()))
        # The checkpoint exists, we're not going to try to upgrade the ports resource
        if not os.access(checkpoint_path, os.R_OK):
            new_resources = list(map(maybe_augment_resource, resources))
            print(RESOURCE_MSG.format(new_resources))
            env_file.write(RESOURCES_TEMPLATE.format(res=json.dumps(new_resources)))

        print(FILE_MSG.format(output_env_file))

    # Now rename tmp file to final file. This guarantees that anything reading
    # this file never sees a "partial" version of the file. It either doesn't
    # exist or it is there with full contents.
    os.rename(tmp_file, output_env_file)

if __name__ == '__main__':
    main(sys.argv[1])
