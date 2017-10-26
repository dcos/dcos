#!/opt/mesosphere/bin/python

"""
The script allows to add network interfaces and ip addresses multiple times
ip command returns 2 as exit code if interface or ipaddr already exists [1]
dcos-net-setup.py checks output of ip command and returns success exit code [2]

[1] ExecStartPre=-/usr/bin/ip link add name type dummy
[2] ExecStartPre=/path/dcos-net-setup.py ip link add name type dummy
"""

import os
import subprocess
import sys


def main():
    if sys.argv[1:4] in [['ip', 'link', 'add'], ['ip', 'addr', 'add']]:
        result = subprocess.run(sys.argv[1:], stderr=subprocess.PIPE)
        sys.stderr.buffer.write(result.stderr)
        if result.stderr.strip().endswith(b'File exists'):
            result.returncode = 0
        sys.exit(result.returncode)
    else:
        os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
