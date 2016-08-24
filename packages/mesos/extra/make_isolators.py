#!/opt/mesosphere/bin/python3

import os
import subprocess
import sys


class IsolatorDiscoveryException(Exception):
        pass


def has_nvidia():
    """
    Test if we have nvidia-smi available and it runs correctly
    """
    nvidia_smi_binary = '/bin/nvidia-smi'

    if not os.path.isfile(nvidia_smi_binary):
        return False
    if not os.access(nvidia_smi_binary, os.X_OK):
        return False

    proc = subprocess.Popen([nvidia_smi_binary, '-L'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    (stdout, stderr) = proc.communicate()
    proc.wait()

    if proc.returncode != 0:
        return False

    return True


def main(output_env_file):
    """
    This script detects if nVidia driver is available
    and if yes, it appends the gpu/nvidia isolator

    @type output_env_file: str
    """

    isolators = os.environ.get('MESOS_ISOLATION', '')

    if has_nvidia():

        if isolators:
            isolators += ','

        if 'cgroups/devices' not in isolators:
            isolators += 'cgroups/devices,'

        isolators += 'gpu/nvidia'

    with open(output_env_file, 'w') as f:
        f.write('MESOS_ISOLATION=%s\n' % isolators)


if __name__ == '__main__':
        try:
                main(sys.argv[1])
        except KeyError as e:
                print('ERROR: Missing key {}'.format(e), file=sys.stderr)
                sys.exit(1)
        except IsolatorDiscoveryException as e:
                print('ERROR: {}'.format(e), file=sys.stderr)
                sys.exit(1)
