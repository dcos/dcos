import pycodestyle

from __version__ import PLUGIN_NAME, PLUGIN_VERSION
from check_rules import regex_rules


def flake8extn(func):
    """Decorator to Specify flake8 extension details."""
    func.version = PLUGIN_VERSION
    func.name = PLUGIN_NAME
    return func


@flake8extn
def check(physical_line):
    if pycodestyle.noqa(physical_line):
        return
    for rule in regex_rules:
        match = rule.regex.search(physical_line)
        if match:
            return match.start(), "{code} {reason}".format(code=rule.code, reason=rule.reason)
