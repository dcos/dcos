#!/usr/bin/env python3
import sys

from dcos_installer import DcosInstaller


def main():
    if len(sys.argv[1:]) == 0:
        DcosInstaller(["--genconf"])
    else:
        DcosInstaller(sys.argv[1:])

if __name__ == '__main__':
    main()
