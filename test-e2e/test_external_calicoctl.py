"""
Test external calicoctl
"""
import os
import platform
import stat
import subprocess
import uuid
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import pytest
import requests
from _pytest.fixtures import SubRequest
from _pytest.tmpdir import TempdirFactory
from cluster_helpers import wait_for_dcos_oss
from conditional import E2E_SAFE_DEFAULT, escape, only_changed, trailing_path
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Output


@pytest.fixture(scope='module')
def calicoctl(tmpdir_factory: TempdirFactory) -> Callable[[List[str],
                                                           Optional[dict]],
                                                          dict]:
    tmpdir = tmpdir_factory.mktemp('calicoctl')
    path = os.path.join(str(tmpdir), "calicoctl")
    system = platform.system().lower()
    download_url = ('https://downloads.mesosphere.io/dcos-calicoctl/bin'
                    '/v3.12.0-d2iq.1/fd5d699-b80546e'
                    '/calicoctl-{}-amd64').format(system)

    with open(path, 'wb') as f:
        r = requests.get(download_url, stream=True, verify=True)
        for chunk in r.iter_content(8192):
            f.write(chunk)

    # make binary executable
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC)

    def exec(cmd: List[str],
             env: Optional[dict] = None) -> dict:

        process = subprocess.run([path] + cmd,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 env=env)

        return {
            'stdout': process.stdout.decode('utf-8'),
            'stderr': process.stderr.decode('utf-8'),
            'returncode': process.returncode,
        }

    return exec


@pytest.mark.skipif(
    only_changed(E2E_SAFE_DEFAULT + [
        # All packages safe except named packages
        'packages/*/**',
        '!packages/{adminrouter,bouncer,calico,etcd,openssl}/**',
        '!packages/python*/**',
        # All e2e tests safe except this test
        'test-e2e/test_*', '!' + escape(trailing_path(__file__, 2)),
    ]),
    reason='Only safe files modified',
)
def test_access(docker_backend: Docker,
                artifact_path: Path,
                request: SubRequest,
                log_dir: Path,
                rsa_keypair: Tuple[str, str],
                jwt_token: Callable[[str, str, int], str],
                calicoctl: Callable[[List[str], Optional[dict]], dict],
                ) -> None:
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
        env = {
            'ETCD_ENDPOINTS': 'http://{}:12379'.format(master_ip),
        }

        result = calicoctl(['get', 'nodes'], env)
        assert 'access denied' in result['stderr']
        assert result['returncode'] != 0

        authorization = 'authorization:token={}'.format(token)
        env['ETCD_CUSTOM_GRPC_METADATA'] = authorization
        result = calicoctl(['get', 'nodes'], env)
        assert 'NAME' in result['stdout']
        assert result['returncode'] == 0
