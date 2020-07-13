"""
Surrogate conftest.py contents loaded by the conftest.py file.
"""
import logging
import os
from pathlib import Path
from typing import Generator

import pytest
from _pytest.fixtures import SubRequest
from cluster_helpers import wait_for_dcos_oss
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster


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


@pytest.fixture
def three_master_cluster(
    artifact_path: Path,
    docker_backend: Docker,
    request: SubRequest,
    log_dir: Path,
) -> Generator[Cluster, None, None]:
    """Spin up a highly-available DC/OS cluster with three master nodes."""
    with Cluster(
        cluster_backend=docker_backend,
        masters=3,
        agents=0,
        public_agents=0,
    ) as cluster:
        cluster.install_dcos_from_path(
            dcos_installer=artifact_path,
            dcos_config=cluster.base_config,
            ip_detect_path=docker_backend.ip_detect_path,
        )
        wait_for_dcos_oss(
            cluster=cluster,
            request=request,
            log_dir=log_dir,
        )
        yield cluster
