import os
import random
import string
from pathlib import Path

import pytest
from _pytest.fixtures import SubRequest
from cluster_helpers import (
    wait_for_dcos_oss,
)
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Output


@pytest.fixture(scope='module')
def workspace_dir() -> Path:
    """
    Creates a known workspace directory.
    """
    tmp_dir_path = Path(os.environ['DCOS_E2E_TMP_DIR_PATH'])
    assert tmp_dir_path.exists() and tmp_dir_path.is_dir()

    subpath = ''.join(random.choice(string.ascii_lowercase) for i in range(5))

    return tmp_dir_path / subpath


def test_windows_agents(
    workspace_dir: Path,
    artifact_path: Path,
    request: SubRequest,
    log_dir: Path,
) -> None:
    """
    Enabling Windows agents creates additional configuration package
    and does not break Linux installation.
    """
    docker_backend = Docker(workspace_dir=workspace_dir)

    config = {
        'enable_windows_agents': True,
    }
    with Cluster(
        cluster_backend=docker_backend,
        agents=0,
        public_agents=0,
    ) as cluster:
        cluster.install_dcos_from_path(
            dcos_installer=artifact_path,
            dcos_config={
                **cluster.base_config,
                **config,
            },
            output=Output.LOG_AND_CAPTURE,
            ip_detect_path=docker_backend.ip_detect_path,
        )

        # Check that dcos-config-win.tar.xz was created
        paths = []
        for root, _, files in os.walk(str(workspace_dir)):
            for file in files:
                if file.startswith('dcos-config-win--setup_'):
                    paths.append(Path(root) / file)
        assert len(paths) == 1

        wait_for_dcos_oss(
            cluster=cluster,
            request=request,
            log_dir=log_dir,
        )
