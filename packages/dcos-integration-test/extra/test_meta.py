"""
Tests for the integration test suite itself.
"""

import logging
import os
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Set

import yaml

from get_test_group import patterns_from_group

__maintainer__ = 'adam'
__contact__ = 'tools-infra-team@mesosphere.io'

log = logging.getLogger(__file__)


def _tests_from_pattern(ci_pattern: str, cwd: str) -> Set[str]:
    """
    From a CI pattern, get all tests ``pytest`` would collect.
    """
    tests = set([])  # type: Set[str]
    args = [
        'pytest',
        '--disable-pytest-warnings',
        '--collect-only',
        ci_pattern,
        '-q',
    ]
    # Test names will not be in ``stderr`` so we ignore that.
    result = subprocess.run(
        args=args,
        stdout=subprocess.PIPE,
        env={**os.environ, **{'PYTHONIOENCODING': 'UTF-8'}},
        cwd=cwd
    )
    output = result.stdout
    for line in output.splitlines():
        if b'error in' in line:
            message = (
                'Error collecting tests for pattern "{ci_pattern}". '
                'Full output:\n'
                '{output}'
            ).format(
                ci_pattern=ci_pattern,
                output=output.decode(),
            )
            raise Exception(message)
        # Whitespace is important to avoid confusing pytest warning messages
        # with test names. For example, the pytest output may contain '3 tests
        # deselected' which would conflict with a test file called
        # test_agent_deselected.py if we ignored whitespace.
        if (
            line and
            # Some tests show warnings on collection.
            b' warnings' not in line and
            # Some tests are skipped on collection.
            b'skipped in' not in line and
            # Some tests are deselected by the ``pytest.ini`` configuration.
            b' deselected' not in line and
            not line.startswith(b'no tests ran in')
        ):
            tests.add(line.decode())

    return tests


def test_test_groups() -> None:
    """
    The test suite is split into various "groups".
    This test confirms that the groups together contain all tests, and each
    test is collected only once.
    """
    test_groups_path = 'test_groups.yaml'
    if 'pyexecnetcache' in os.getcwd():
        # We are running this from outside the cluster using pytest-xdist, so test_groups.yaml won't be in the current
        # working directory. It will be in /extra
        test_groups_path = os.path.join('extra', test_groups_path)
    else:
        test_groups_path = os.path.join(os.getcwd(), test_groups_path)

    test_group_file = Path(test_groups_path)
    test_group_file_contents = test_group_file.read_text()
    test_groups = yaml.safe_load(test_group_file_contents)['groups']
    test_patterns = []
    for group in test_groups:
        test_patterns += patterns_from_group(group_name=group, test_groups_path=test_groups_path)

    # Turn this into  a list otherwise we can't cannonically state whether every test was collected _exactly_ once :-)
    tests_to_patterns = defaultdict(list)
    for pattern in test_patterns:
        tests = _tests_from_pattern(ci_pattern=pattern, cwd=os.path.dirname(test_groups_path))
        for test in tests:
            tests_to_patterns[test].append(pattern)

    errs = []
    for test_name, patterns in tests_to_patterns.items():
        message = (
            'Test "{test_name}" will be run once for each pattern in '
            '{patterns}. '
            'Each test should be run only once.'
        ).format(
            test_name=test_name,
            patterns=patterns,
        )
        if len(patterns) != 1:
            assert len(patterns) != 1, message
            errs.append(message)

    if errs:
        for message in errs:
            log.error(message)
        raise Exception("Some tests are not collected exactly once, see errors.")

    all_tests = _tests_from_pattern(ci_pattern='', cwd=os.path.dirname(test_groups_path))
    assert tests_to_patterns.keys() - all_tests == set()
    assert all_tests - tests_to_patterns.keys() == set()
