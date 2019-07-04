"""
Surrogate conftest.py contents loaded by the conftest.py file.
"""
import logging
import os
from pathlib import Path

import pytest

from dcos_e2e.backends import Docker


@pytest.fixture(scope='session', autouse=True)
def configure_logging() -> None:
    """
    Surpress INFO, DEBUG and NOTSET log messages from libraries that log
    excessive amount of debug output that isn't useful for debugging e2e tests.
    """
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARN)
    logging.getLogger('docker').setLevel(logging.WARN)
    logging.getLogger('sarge').setLevel(logging.WARN)


@pytest.fixture(scope='session')
def docker_backend() -> Docker:
    """
    Creates a common Docker backend configuration that works within the pytest
    environment directory.
    """
    tmp_dir_path = Path(os.environ['DCOS_E2E_TMP_DIR_PATH'])
    assert tmp_dir_path.exists() and tmp_dir_path.is_dir()

    return Docker(workspace_dir=tmp_dir_path)


@pytest.fixture(scope='session')
def artifact_path() -> Path:
    """
    Return the path to a DC/OS build artifact to test against.
    """
    generate_config_path = Path(os.environ['DCOS_E2E_GENCONF_PATH'])
    return generate_config_path


@pytest.fixture(scope='session')
def log_dir() -> Path:
    """
    Return the path to a directory which logs should be stored in.
    """
    return Path(os.environ['DCOS_E2E_LOG_DIR'])
