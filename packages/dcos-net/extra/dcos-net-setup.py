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

import os
import shutil
import subprocess
import sys


def main():
    if sys.argv[1:4] in [['ip', 'link', 'add'], ['ip', 'addr', 'add'], ['ip', '-6', 'addr']]:
        result = subprocess.run(sys.argv[1:], stderr=subprocess.PIPE)
        sys.stderr.buffer.write(result.stderr)
        if result.stderr.strip().endswith(b'File exists'):
            result.returncode = 0
    elif sys.argv[1] == 'iptables':
        # check whether a rule matching the specification does exist
        argv = ['-C' if arg in ['-A', '-I'] else arg for arg in sys.argv[1:]]
        result = subprocess.run(argv)
        if result.returncode != 0:
            # if it doesn't exist append or insert that rules
            result = subprocess.run(sys.argv[1:])
    elif sys.argv[1] == '--ipv6':
        if os.getenv('DCOS_NET_IPV6', 'true') == 'false':
            sys.exit(0)
        else:
            del sys.argv[1]
            result = subprocess.run(sys.argv)
    elif sys.argv[1:3] == ['networkd', 'add'] and len(sys.argv) == 4:
        result = add_networkd_config(sys.argv[3])
    else:
        result = subprocess.run(sys.argv[1:])
    sys.exit(result.returncode)


def add_networkd_config(src):
    networkd = b'systemd-networkd.service'

    # check if there is networkd
    result = subprocess.run(['systemctl', 'list-unit-files', networkd],
                            stdout=subprocess.PIPE)
    if result.returncode != 0:
        return result
    if networkd not in result.stdout:
        return result

    # copy the configuration
    bname = os.path.basename(src)
    dst = os.path.join('/etc/systemd/network', bname)
    shutil.copyfile(src, dst)

    # Restart networkd only if it's active
    result = subprocess.run(['systemctl', 'is-active', networkd],
                            stdout=subprocess.PIPE)
    if result.returncode != 0:
        result.returncode = 0
        return result

    return subprocess.run(['systemctl', 'restart', networkd])


if __name__ == "__main__":
    main()
