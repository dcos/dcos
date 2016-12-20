import re

from collections import namedtuple

CheckRegex = namedtuple("CheckRegex", "regex code reason")


regex_rules = [
    CheckRegex(re.compile(r'assert\s(\w+\.ok)$'), "D001", "Invalid assertion of type assert <symbol>.ok found.")
]
