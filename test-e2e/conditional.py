import logging
import os
from typing import Any, cast, Dict, Iterator, Optional, Tuple

import requests


CI_UNKNOWN = 'unknown'
CI_RELEASE = 'release'
CI_TRAIN = 'train'
CI_PULL_REQUEST = 'PR'
CI_EXTERNAL = 'external'


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


def get_modified_files(sha_comparison: Dict[str, Any]) -> Iterator[str]:
    return cast(Iterator[str], [file['filename'] for file in sha_comparison['files']])


def log_modified_files() -> None:
    github_type, pr_id = github_pr_id()
    if pr_id is None:
        logging.info('GitHub type: %s', github_type)
        return
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
        if info['user']['login'] == 'mesosphere-mergebot':
            logging.info('PR appears to be a train')
    except Exception:
        logging.exception('Failed to get modified files')
