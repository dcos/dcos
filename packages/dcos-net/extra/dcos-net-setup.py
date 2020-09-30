#!/opt/mesosphere/bin/python

"""
The script allows to add network interfaces and ip addresses multiple times
ip command returns 2 as exit code if interface or ipaddr already exists [1]
dcos-net-setup.py checks output of ip command and returns success exit code [2]

[1] ExecStartPre=-/usr/bin/ip link add name type dummy
[2] ExecStartPre=/path/dcos-net-setup.py ip link add name type dummy

Also the script prevents from duplicating iptables rules [3]

[3] ExecStartPre=/path/dcos-net-setup.py iptables --wait -A FORWARD -j ACCEPT

The script allows to add configuration for networkd
"""

import filecmp
import os
import platform
import shutil
import subprocess
import sys

DEBUG = os.environ.get('DCOS_NET_STARTUP_DEBUG')


def run(cmd, *args, **kwargs):
    command = ' '.join(cmd)

    if DEBUG:
        print('command: `{}`'.format(command))

    result = subprocess.run(cmd, *args, **kwargs)
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)

    if DEBUG:
        print('command: `{}` exited with status `{}`'.format(
            command,
            result.returncode,
        ))

    return result


def main():
    return_code = 0
    if sys.argv[1:4] in [['ip', 'link', 'add'], ['ip', 'addr', 'add'], ['ip', '-6', 'addr']]:
        result = run(sys.argv[1:], stderr=subprocess.PIPE)
        sys.stderr.buffer.write(result.stderr)
        if result.stderr.strip().endswith(b'File exists'):
            result.returncode = 0
        return_code = result.returncode
    elif sys.argv[1] == 'iptables':
        # check whether a rule matching the specification does exist
        argv = ['-C' if arg in ['-A', '-I'] else arg for arg in sys.argv[1:]]
        result = run(argv)
        if result.returncode != 0:
            # if it doesn't exist append or insert that rules
            result = run(sys.argv[1:])
        return_code = result.returncode
    elif sys.argv[1] == '--ipv6':
        if os.getenv('DCOS_NET_IPV6', 'true') == 'false':
            sys.exit(0)
        else:
            del sys.argv[1]
            result = run(sys.argv)
            return_code = result.returncode
    elif sys.argv[1:3] == ['networkd', 'add'] and len(sys.argv) == 4:
        return_code = add_networkd_config(sys.argv[3])
    else:
        result = run(sys.argv[1:])
        return_code = result.returncode
    sys.exit(return_code)


def check_for_unit(unit: str) -> int:
    result = run(['systemctl', 'list-unit-files', unit],
                 stdout=subprocess.PIPE)

    if result.returncode == 0 and unit in result.stdout.decode():
        return 0

    return result.returncode


def is_unit_active(unit: str) -> bool:
    result = run(['systemctl', 'is-active', unit],
                 stdout=subprocess.PIPE)
    if result.returncode == 0:
        return True

    return False


def copy_file(src, dst) -> bool:
    try:
        if not filecmp.cmp(src, dst):
            return bool(shutil.copyfile(src, dst))

        return False
    except FileNotFoundError:
        return bool(shutil.copyfile(src, dst))


def add_networkd_config(src: str) -> int:
    # systemd-networkd, when enabled, will wipe the configurations like IP
    # address of network interfaces and this behavior happens only on coreos
    # This problem is tracked by:
    # https://jira.mesosphere.com/browse/DCOS_OSS-1790
    # We need to mark interfaces managed by DC/OS as unmanaged when networkd is
    # enabled on coreos
    if platform.system() != "Linux" or "coreos" not in platform.release():
        return 0

    networkd = 'systemd-networkd.service'
    networkd_path = '/etc/systemd/network'

    # Check if there is networkd
    result = check_for_unit(networkd)
    if result.returncode != 0:
        return result.returncode

    # Copy the configuration
    bname = os.path.basename(src)
    dst = os.path.join(networkd_path, bname)

    # Ensure the destination directory exists
    os.makedirs(networkd_path, mode=0o755, exist_ok=True)

    replaced = copy_file(src, dst)

    # Restart networkd only if it's active
    if not is_unit_active(networkd):
        return 0

    # Restart networkd only if the configuration is updated
    if replaced:
        return run(['systemctl', 'restart', networkd]).returncode

    return 0


if __name__ == "__main__":
    main()
