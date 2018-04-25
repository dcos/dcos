try:
    import fcntl
except ImportError:
    pass
import logging
import os
import sys

from pkgpanda.util import is_windows

if not is_windows:
    assert 'fcntl' in sys.modules

log = logging.getLogger(__name__)


def read_file_line(filename):
    with open(filename, 'r') as f:
        return f.read().strip()


class Directory:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        log.info('Opening {}'.format(self.path))
        self.fd = os.open(self.path, os.O_RDONLY)
        log.info('Opened {} with fd {}'.format(self.path, self.fd))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        log.info('Closing {} with fd {}'.format(self.path, self.fd))
        os.close(self.fd)

    def lock(self):
        return Flock(self.fd, fcntl.LOCK_EX)


class Flock:
    def __init__(self, fd, op):
        (self.fd, self.op) = (fd, op)

    def __enter__(self):
        log.info('Locking fd {}'.format(self.fd))
        # If the fcntl() fails, an IOError is raised.
        fcntl.flock(self.fd, self.op)
        log.info('Locked fd {}'.format(self.fd))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        log.info('Unlocked fd {}'.format(self.fd))
