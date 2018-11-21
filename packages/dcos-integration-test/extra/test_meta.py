"""
Tests for the integration test suite itself.
"""

import subprocess
from pathlib import Path
from typing import Set

from get_test_group import patterns_from_group


def _tests_from_pattern(ci_pattern: str) -> Set[str]:
    """
    From a CI pattern, get all tests ``pytest`` would collect.
    """
    tests = set([])  # type: Set[str]
    args = ['pytest', '--collect-only', ci_pattern, '-q']
    result = subprocess.run(args=args, stdout=subprocess.PIPE)
    output = result.stdout
    for line in output.splitlines():
        if line and not line.startswith(b'no tests ran in'):
            tests.add(line.decode())

    return tests


def test_test_groups() -> None:
    """
    The test suite is split into various "groups".
    This test confirms that the groups together contain all tests, and each
    test is collected only once.
    """
    test_group_file = Path('test_groups.yaml')
    test_group_file_contents = test_group_file.read_text()
    test_groups = yaml.load(test_group_file_contents)['groups']
    test_patterns = []
    for group in test_groups:
        test_patterns += patterns_from_group(group_name=group)

    tests_to_patterns = {}  # type: Dict[str, Set[str]]
    for pattern in test_patterns:
        tests = _tests_from_pattern(ci_pattern=pattern)
        for test in tests:
            if test in tests_to_patterns:
                tests_to_patterns[test].add(pattern)
            else:
                tests_to_patterns[test] = set([pattern])

    for test_name, patterns in tests_to_patterns.items():
        message = (
            'Test "{test_name}" will be run once for each pattern in '
            '{patterns}. '
            'Each test should be run only once.'
        ).format(
            test_name=test_name,
            patterns=patterns,
        )
        assert len(patterns) == 1, message

    all_tests = _tests_from_pattern(ci_pattern='')
    assert tests_to_patterns.keys() - all_tests == set()
    assert all_tests - tests_to_patterns.keys() == set()
