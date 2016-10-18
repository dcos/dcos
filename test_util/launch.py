"""

Usage:
dcos-launch create [--wait] [--dump-info=cluster_info.json] <config=config.yaml>
dcos-launch wait <path=cluster_info.json>
dcos-launch describe <path=cluster_info.json>
dcos-launch delete <path=cluster_info.json>
"""

from docopt import docopt


def main():
    docopt(__doc__)

    raise NotImplementedError()


if __name__ == '__main__':
    main()
