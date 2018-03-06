#!/opt/mesosphere/bin/python

"""
The script allows to add network interfaces and ip addresses multiple times
ip command returns 2 as exit code if interface or ipaddr already exists [1]
dcos-net-setup.py checks output of ip command and returns success exit code [2]

[1] ExecStartPre=-/usr/bin/ip link add name type dummy
[2] ExecStartPre=/path/dcos-net-setup.py ip link add name type dummy

Also the script prevents from duplicating iptables rules [3]

[3] ExecStartPre=/path/dcos-net-setup.py iptables --wait -A FORWARD -j ACCEPT
"""

import os
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
    else:
        result = subprocess.run(sys.argv[1:])
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
