import logging
import os
import subprocess

import portalocker

import gen


log = logging.getLogger(__name__)


def read_file_line(filename):
    with open(filename, 'r') as f:
        return f.read().strip()


def detect_ip():
    cmd = ['/opt/mesosphere/bin/detect_ip']
    machine_ip = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('ascii').strip()
    gen.calc.validate_ipv4_addresses([machine_ip])
    return machine_ip


class Directory:
    def __init__(self, path):
        # open does not support directories, so use file in directory
        self.path = path + os.sep + ".directorylock"

    def __enter__(self):
        log.info('Opening {}'.format(self.path))
        self.fd = open(self.path, "w")
        log.info('Opened {} with fd {}'.format(self.path, self.fd))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        log.info('Closing {} with fd {}'.format(self.path, self.fd))
        self.fd.close()

    def lock(self):
        return Flock(self.fd, portalocker.LOCK_EX)


class Flock:
    def __init__(self, fd, op):
        (self.fd, self.op) = (fd, op)

    def __enter__(self):
        log.info('Locking fd {}'.format(self.fd))
        # If the fcntl() fails, an IOError is raised.
        portalocker.lock(self.fd, self.op)
        log.info('Locked fd {}'.format(self.fd))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        portalocker.unlock(self.fd)
        log.info('Unlocked fd {}'.format(self.fd))
