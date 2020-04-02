
import logging
import subprocess
from subprocess import CalledProcessError, PIPE, Popen  # noqa: F401

logger = logging.getLogger(__name__)


def call(*args, **kwargs):
    if len(args) > 0:
        logger.debug(' '.join(args[0]))
    return subprocess.call(*args, **kwargs)


def check_call(*args, **kwargs):
    if len(args) > 0:
        logger.debug(' '.join(args[0]))
    return subprocess.check_call(*args, **kwargs)


def check_output(*args, **kwargs):
    if len(args) > 0:
        logger.debug(' '.join(args[0]))
    return subprocess.check_output(*args, **kwargs)
