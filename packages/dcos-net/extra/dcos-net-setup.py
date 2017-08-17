#!/opt/mesosphere/bin/python

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
