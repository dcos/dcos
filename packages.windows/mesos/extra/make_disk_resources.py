#!/opt/mesosphere/bin/python3

import json
import os
import re
import shutil
import subprocess
import sys

from datetime import datetime
from itertools import chain
from math import floor
from string import Template


PROG = os.path.basename(__file__)

JSON_COMMON_TEMPLATE = Template('''
{
    "name": "disk",
    "role": "$role",
    "scalar": {
        "value": $free_space
    },
    "type": "SCALAR"
}
''')

JSON_DISK_TEMPLATE = Template('''
{
    "disk": {
        "source": {
            "type": "MOUNT",
            "mount": {
                "root": "$mp"
            }
        }
    }
}
''')

MOUNT_PATTERN = re.compile('on\s+(/dcos/volume\d+)\s+', re.M | re.I)

# Conversion factor for Bytes -> MB calculation
MB = float(1 << 20)

TOLERANCE_MB = 100

RESOURCES_TEMPLATE_HEADER = '''# Generated by {prog} on {dt}
#
'''

RESOURCES_TEMPLATE = '''
MESOS_RESOURCES='{res}'
'''


class VolumeDiscoveryException(Exception):
    pass


def find_mounts_matching(pattern):
    '''
    find all matching mounts from the output of the mount command
    '''
    print('Looking for mounts matching pattern "{}"'.format(pattern.pattern))
    mounts = subprocess.check_output(['mount'], universal_newlines=True)
    return pattern.findall(mounts)


def make_disk_resources_json(mounts, role):
    '''
    Disk resources are defined in https://mesos.apache.org/documentation/latest/multiple-disk/

    Substitute discovered mounts into JSON_TEMPLATE, returning a list of Mounts

    @type mounts: tuple(mount_point, free_space_in_mb)
    @rtype: list
    '''
    for (mp, fs) in mounts:
        common = JSON_COMMON_TEMPLATE.substitute(free_space=fs, role=role)
        disk = JSON_DISK_TEMPLATE.substitute(mp=mp)
        yield json.loads(common), json.loads(disk)


def get_disk_free(path):
    '''
    @type path: str

    @rtype tuple
    '''
    return (path, floor(float(shutil.disk_usage(path).free) / MB))


def get_mounts_and_freespace(matching_mounts):
    for mount, free_space in map(get_disk_free, matching_mounts):
        net_free_space = free_space - TOLERANCE_MB
        if net_free_space <= 0:
            # Per @cmaloney and @lingmann, we should hard exit here if volume
            # doesn't have sufficient space.
            raise VolumeDiscoveryException(
                '{} has {} MB net free space, expected > 100M'.format(mount, net_free_space)
            )
        yield (mount, net_free_space)


def _handle_root_volume(root_volume, role):
    os.makedirs(root_volume, exist_ok=True)
    for common, _ in make_disk_resources_json(get_mounts_and_freespace([root_volume]), role):
        yield common, {}


def stitch(parts):
    common, disk = parts
    common.update(disk)
    return common


def main(output_env_file):
    '''
    Find mounts and freespace matching MOUNT_PATTERN, create RESOURCES for the
    disks, and merge the list of disk resources with optionally existing
    MESOS_RESOURCES environment varianble.

    @type output_env_file: str, filename to write resources
    '''
    if os.path.exists(output_env_file):
        print('Volume discovery assumed to be completed because {} exists'.format(output_env_file))
        return

    mounts_dfree = list(get_mounts_and_freespace(find_mounts_matching(MOUNT_PATTERN)))
    print('Found matching mounts : {}'.format(mounts_dfree))

    role = os.getenv('MESOS_DEFAULT_ROLE', '*')

    disk_resources = list(
        map(
            stitch, chain(
                make_disk_resources_json(mounts_dfree, role),
                _handle_root_volume(os.environ['MESOS_WORK_DIR'], role)
            )
        )
    )
    print('Generated disk resources map: {}'.format(disk_resources))

    # write contents to a temporary file
    tmp_file = '{}.tmp'.format(output_env_file)
    with open(tmp_file, 'w') as env_file:
        env_file.write(RESOURCES_TEMPLATE_HEADER.format(prog=PROG, dt=datetime.now()))
        if disk_resources:
            msg = 'Creating updated environment artifact file : {}'
            env_resources = os.environ.get('MESOS_RESOURCES', '[]')
            try:
                resources = json.loads(env_resources)
            except ValueError as e:
                print('ERROR: Invalid MESOS_RESOURCES JSON {} --- {}'.format(e, env_resources), file=sys.stderr)
                sys.exit(1)
            resources.extend(disk_resources)
            env_file.write(RESOURCES_TEMPLATE.format(res=json.dumps(resources)))
        else:
            msg = 'No additional volumes. Empty artifact file {} created'

    print(msg.format(output_env_file))

    # Now rename tmp file to final file. This guarantees that anything reading
    # this file never sees a "partial" version of the file. It either doesn't
    # exist or it is there with full contents.
    os.rename(tmp_file, output_env_file)


if __name__ == '__main__':
    try:
        main(sys.argv[1])
    except KeyError as e:
        print('ERROR: Missing key {}'.format(e), file=sys.stderr)
        sys.exit(1)
    except VolumeDiscoveryException as e:
        print('ERROR: {}'.format(e), file=sys.stderr)
        sys.exit(1)
