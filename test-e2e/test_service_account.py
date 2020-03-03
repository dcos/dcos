import uuid
from pathlib import Path
from typing import Callable, Tuple

import requests
from _pytest.fixtures import SubRequest
from cluster_helpers import (
    wait_for_dcos_oss,
)
from dcos_e2e.base_classes import ClusterBackend
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Output


def test_superuser_service_account_login(
    docker_backend: ClusterBackend,
    artifact_path: Path,
    request: SubRequest,
    log_dir: Path,
    rsa_keypair: Tuple[str, str],
    jwt_token: Callable[[str, str, int], str]
) -> None:
    """
    Tests for successful superuser service account login which asserts
    that the default user has been created during cluster start.
    """
    superuser_uid = str(uuid.uuid4())
    config = {
        'superuser_service_account_uid': superuser_uid,
        'superuser_service_account_public_key': rsa_keypair[1],
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
        wait_for_dcos_oss(
            cluster=cluster,
            request=request,
            log_dir=log_dir,
        )
        master = next(iter(cluster.masters))
        master_url = 'http://' + str(master.public_ip_address)
        login_endpoint = master_url + '/acs/api/v1/auth/login'

        service_login_token = jwt_token(superuser_uid, rsa_keypair[0], 30)

        response = requests.post(
            login_endpoint,
            json={'uid': superuser_uid, 'token': service_login_token}
        )
        assert response.status_code == 200
