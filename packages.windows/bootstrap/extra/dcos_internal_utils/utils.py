import logging
import os
import portalocker

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
        return Flock(self.fd)


class Flock:
    def __init__(self, fd):
        (self.fd) = (fd)

    def __enter__(self):
        log.info('Locking fd {}'.format(self.fd))
        # If the fcntl() fails, an IOError is raised.
        portalocker.lock(self.fd)
        log.info('Locked fd {}'.format(self.fd))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        portalocker.unlock(self.fd)
        log.info('Unlocked fd {}'.format(self.fd))
