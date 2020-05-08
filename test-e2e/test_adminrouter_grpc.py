"""
Test the adminrouter grpc proxy
"""
import random
import uuid
from pathlib import Path
from typing import Callable, Tuple

import etcd3
import etcd3.etcdrpc
import etcd3.watch
import requests
from _pytest.fixtures import SubRequest
from cluster_helpers import wait_for_dcos_oss
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Output


def test_adminrouter_grpc_proxy_port(docker_backend: Docker,
                                     artifact_path: Path,
                                     request: SubRequest,
                                     log_dir: Path,
                                     rsa_keypair: Tuple[str, str],
                                     jwt_token: Callable[[str, str, int], str]
                                     ) -> None:
    random_port = random.randint(63000, 64000)

    with Cluster(
            cluster_backend=docker_backend,
            masters=1,
            agents=0,
            public_agents=0,
    ) as cluster:
        uid = str(uuid.uuid4())

        config = {
            'superuser_service_account_uid': uid,
            'superuser_service_account_public_key': rsa_keypair[1],
            'adminrouter_grpc_proxy_port': '{}'.format(random_port),
        }

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
        master_ip = master.public_ip_address
        login_endpoint = 'http://{}/acs/api/v1/auth/login'.format(master_ip)
        service_login_token = jwt_token(uid, rsa_keypair[0], 30)

        token_response = requests.post(
            login_endpoint,
            json={'uid': uid, 'token': service_login_token}
        )

        assert token_response.status_code == 200
        token = token_response.json().get('token')

        etcd = etcd3.Etcd3Client(
            host=list(cluster.masters)[0].public_ip_address,
            port=random_port,
            timeout=None,
        )
        etcd.metadata = (('authorization', 'token={}'.format(token)),)
        etcd.watcher = etcd3.watch.Watcher(
            etcd3.etcdrpc.WatchStub(etcd.channel),
            timeout=etcd.timeout,
            call_credentials=etcd.call_credentials,
            metadata=etcd.metadata
        )

        value, meta = etcd.get('probably-invalid-key')
        assert value is None
        assert meta is None
