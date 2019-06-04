import logging
from typing import List

from dcos_installer.constants import CHECK_RUNNER_CMD


log = logging.getLogger(__name__)


def print_header(string):
    delimiter = '====>'
    log.warning('{:5s} {:6s}'.format(delimiter, string))


def is_check_command(cmd: List[str]):
    return CHECK_RUNNER_CMD in ' '.join(cmd)
