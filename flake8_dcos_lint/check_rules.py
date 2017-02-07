import re

from collections import namedtuple

CheckRegex = namedtuple("CheckRegex", "regex code reason")


regex_rules = [
    # Prefer asserting actual == expected, instead of asserting on .ok on a result object.
    # In certain a specific instance, Response object from requests library provides a `ok` short code of type bool
    # that is not documented, and it engulfs the status code. It is better to assert .status_code value there.
    CheckRegex(re.compile(r'assert\s(\w+\.ok)$'), "D001", "Assertion of type assert <symbol>.ok detected.")
]
