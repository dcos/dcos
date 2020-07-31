"""
Usage:

$ python get_test_group.py group_1
test_foo.py test_bar.py::TestClass
$

This is used by CI to run only a certain set of tests on a particular builder.

See ``test_groups.yaml`` for details.
"""

from pathlib import Path
from typing import List

import click
import yaml


def patterns_from_group(group_name: str, test_groups_path: str = 'test_groups.yaml') -> List[str]:
    """
    Given a group name, return all the pytest patterns defined for that group
    in ``test_groups.yaml``.
    """
    test_group_file = Path(test_groups_path)
    test_group_file_contents = test_group_file.read_text()
    test_groups = yaml.safe_load(test_group_file_contents)['groups']
    group = test_groups[group_name]  # type: List[str]
    return group


@click.command('list-integration-test-patterns')
@click.argument('group_name')
def list_integration_test_patterns(group_name: str) -> None:
    """
    Perform a release.
    """
    test_patterns = patterns_from_group(group_name=group_name)
    click.echo(' '.join(test_patterns), nl=False)


if __name__ == '__main__':
    list_integration_test_patterns()
