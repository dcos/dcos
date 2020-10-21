import inspect
import logging
import os
from typing import Any, cast, Dict, Iterator, List, Optional, Tuple

import requests
from wcmatch import glob


# E2E_SAFE_DEFAULT includes files that typically do not affect e2e tests.
# `*.txt` not included here because `requirements.txt` can affect tests.
E2E_SAFE_DEFAULT = [
    # Safe file patterns
    '**/*.md', '**/.git*', '**/LICENSE',
    # Safe directories
    '.github/**', 'config/**', 'docs/**', 'flake8_dcos_lint/**',
    'gen/tests/**', 'teamcity/**', 'test-util/**',
    # Safe files
    '.editorconfig', '.pre-commit-config.yaml', 'Jenkinsfile*', 'NOTICE',
    'owners.json', 'symlink_check', 'tox.ini',
]

CI_UNKNOWN = 'unknown'
CI_RELEASE = 'release'
CI_TRAIN = 'train'
CI_PULL_REQUEST = 'PR'
CI_EXTERNAL = 'external'


def escape(name: str) -> str:
    escaped = glob.escape(name)  # type: str
    return escaped


def trailing_path(path: str, n: int) -> str:
    return '/'.join(path.rsplit('/', n)[-n:])


def github_pr_id() -> Tuple[str, Optional[str]]:
    url = os.environ.get('INSTALLER_URL')
    if url is None:
        # not running in CI
        logging.info('No INSTALLER_URL')
        return CI_EXTERNAL, None

    logging.info('INSTALLER_URL=%s', url)
    parts = url.rsplit('/', 2)
    if len(parts) == 3 and parts[2] == 'dcos_generate_config.sh':
        if parts[0] == 'https://downloads.dcos.io/dcos/testing/pull' and parts[1].isdigit():
            # e.g. https://downloads.dcos.io/dcos/testing/pull/7427/dcos_generate_config.sh
            return CI_PULL_REQUEST, parts[1]

        if parts[0] == 'https://downloads.dcos.io/dcos/testing' and parts[1]:
            # e.g. https://downloads.dcos.io/dcos/testing/master/dcos_generate_config.sh
            logging.info('Release branch: %s', parts[1])
            return CI_RELEASE, None

    logging.info('Unexpected format for INSTALLER_URL')
    return CI_UNKNOWN, None


def github_pr_info(pr_id: str) -> Dict[str, Any]:
    url = 'https://api.github.com/repos/dcos/dcos/pulls/{}'.format(pr_id)
    r = requests.get(url)
    r.raise_for_status()
    remaining = r.headers['X-RateLimit-Remaining']
    logging.info('Remaining requests: %s', remaining)
    return cast(Dict[str, Any], r.json())


def github_pr_compare(base_sha: str, head_sha: str) -> Dict[str, Any]:
    url = 'https://api.github.com/repos/dcos/dcos/compare/{}...{}'.format(
        base_sha, head_sha
    )
    r = requests.get(url)
    r.raise_for_status()
    return cast(Dict[str, Any], r.json())


_known_file_status = frozenset(('added', 'modified', 'removed', 'renamed'))


def get_modified_files(sha_comparison: Dict[str, Any]) -> Iterator[str]:
    result = []
    for file in sha_comparison['files']:
        assert file['status'] in _known_file_status, file
        result.append(file['filename'])
        if file['status'] == 'renamed':
            result.append(file['previous_filename'])
    return cast(Iterator[str], result)


class ChangeDetector:

    def __init__(self) -> None:
        self.changed_files = None  # type: Optional[Tuple[str, Optional[Iterator[str]]]]

    def get_changed_files(self) -> Tuple[str, Optional[Iterator[str]]]:
        result = self.changed_files
        if result is None:
            github_type, pr_id = github_pr_id()
            if pr_id is None:
                logging.info('GitHub type: %s', github_type)
                result = github_type, None
            else:
                try:
                    info = github_pr_info(pr_id)
                    logging.info('Merging %s into %s', info['head']['label'], info['base']['label'])
                    base_sha = info['base']['sha']
                    # Using `info['head']['sha']` will give the latest SHA, but this test may
                    # have been called for an earlier SHA, as given by `BUILD_VCS_NUMBER`
                    head_sha = os.environ.get('BUILD_VCS_NUMBER')
                    if head_sha is None:
                        logging.warn('Environment variable BUILD_VCS_NUMBER not set')
                        head_sha = info['head']['sha']
                    files = get_modified_files(github_pr_compare(base_sha, head_sha))
                    logging.info('Modified files: %s', files)
                    if (
                        info['user']['login'] == 'mesosphere-mergebot' and
                        'Mergebot Automated Train PR' in info['title']
                    ):
                        logging.info('PR appears to be a train')
                        result = CI_TRAIN, files
                    else:
                        result = CI_PULL_REQUEST, files
                except Exception:
                    logging.exception('Failed to get modified files')
                    result = CI_UNKNOWN, None
            self.changed_files = result
        return result


# Create a single instance to run remote queries once
_change_detector = ChangeDetector()


def only_changed(safelist: List[str], flags: int = glob.BRACE | glob.DOTGLOB | glob.GLOBSTAR | glob.NEGATE) -> bool:
    """
    Return True if we're in a Pull Request and the only files changed by this PR are in
    the `safelist`. This function can be used to skip tests if only files named in the
    `safelist` have been modified.
    """
    # Ensure flags enable globstar required for default safelist
    flags |= glob.GLOBSTAR
    github_type, files_changed = _change_detector.get_changed_files()
    if github_type == CI_PULL_REQUEST:
        # use supplied safelist
        pass
    elif github_type == CI_TRAIN:
        # For trains we want to run if the build has been affected in any way,
        # but can skip for changes that do not affect the build or installation
        # of DC/OS. To do this, skip e2e tests only when files in the default
        # safelist are changed.
        safelist = E2E_SAFE_DEFAULT
    else:
        # return False for all other types to force all tests.
        return False
    assert files_changed is not None
    matches = glob.globfilter(files_changed, safelist, flags=flags)
    not_safe = set(files_changed) - set(matches)
    # When used in a `skipif`, this function is called during collection, so is
    # logged away from the test. Add the file and lineno to identify the test.
    caller = inspect.stack()[1]
    caller_id = '{}:{}'.format(trailing_path(caller.filename, 2), caller.lineno)
    if not_safe:
        logging.info('%s: Changed files not in safelist: %s', caller_id, tuple(not_safe))
        return False
    else:
        logging.info('%s: All changed files in safelist', caller_id)
        return True
