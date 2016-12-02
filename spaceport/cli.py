"""DC/OS Spaceport: Configuration, Assemble, Launch, and Update DC/OS

Usage:
  dcos-spaceport launch
  dcos-spaceport configure
  dcos-spaceport configure aws-advanced
  dcos-spaceport configure azure-advanced
  dcos-spaceport configure ssh
  dcos-spaceport web
"""

from docopt import docopt


def main():
    docopt(__doc__)


if __name__ == '__main__':
    main()
