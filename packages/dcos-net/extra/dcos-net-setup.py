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
NETWORKD = os.environ.get('DCOS_NET_CONFIG_NETWORKD')
NETWORK_MANAGER = os.environ.get('DCOS_NET_CONFIG_NETWORKD')


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
    elif sys.argv[1:3] == ['networkmanager', 'add'] and len(sys.argv) == 4:
        return_code = add_networkmanager_config(sys.argv[3])
    else:
        result = run(sys.argv[1:])
        return_code = result.returncode
    sys.exit(return_code)


def check_for_unit(unit: str) -> int:
    result = run(['systemctl', 'list-unit-files', unit],
                 stdout=subprocess.PIPE)

    # NOTE(jkoelker) Use a negative return code as a signal that the unit
    #                does not exist.
    if result.returncode == 0 and unit not in result.stdout.decode():
        return -1

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
            shutil.copyfile(src, dst)
            return True

        return False
    except FileNotFoundError:
        shutil.copyfile(src, dst)
        return True


def add_config(unit: str, path: str, src: str) -> int:
    # Check if the unit exists
    result = check_for_unit(unit)
    if result < 0:
        if DEBUG:
            print('Unit {} does not exist'.format(unit))
        return 0

    if result != 0:
        if DEBUG:
            print('Error listing units: {}'.format(result))
        return result

    # Copy the configuration
    dst = os.path.join(path, os.path.basename(src))

    # Ensure the destination directory exists
    os.makedirs(path, mode=0o755, exist_ok=True)

    config_replaced = copy_file(src, dst)

    # Restart the unit only if configuration changed and unit is active
    if config_replaced and is_unit_active(unit):
        return run(['systemctl', 'restart', unit]).returncode

    return 0


def add_networkmanager_config(src: str) -> int:
    if NETWORK_MANAGER or 'el' in platform.release():
        return add_config('NetworkManager.service', '/etc/NetworkManager/conf.d', src)

    return 0


def add_networkd_config(src: str) -> int:
    # systemd-networkd, when enabled, will wipe the configurations like IP
    # address of network interfaces and this behavior happens only on coreos
    # This problem is tracked by:
    # https://jira.mesosphere.com/browse/DCOS_OSS-1790
    # We need to mark interfaces managed by DC/OS as unmanaged when networkd is
    # enabled on coreos
    release = platform.release()
    if NETWORKD or 'coreos' in release or 'flatcar' in release:
        return add_config('systemd-networkd.service', '/etc/systemd/network', src)

    return 0


if __name__ == "__main__":
    main()
