import re

from collections import namedtuple

CheckRegex = namedtuple("CheckRegex", "regex code reason")


regex_rules = [
    # Prefer asserting actual == expected, instead of asserting on .ok on a result object.
    CheckRegex(re.compile(r'assert\s(\w+\.ok)$'), "D001", "Assertion of type assert <symbol>.ok detected.")
]
