
import logging
import subprocess
from subprocess import CalledProcessError, PIPE, Popen

logger = logging.getLogger(__name__)

def call(args):
    logger.debug(' '.join(args))
    return subprocess.call(args)

def check_call(args):
    logger.debug(' '.join(args))
    return subprocess.check_call(args)

def check_output(args):
    logger.debug(' '.join(args))
    return subprocess.check_output(args)
