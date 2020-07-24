"""
Surrogate conftest.py contents loaded by the conftest.py file.
"""
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Generator, Tuple

import cryptography.hazmat.backends
import docker
import jwt
import pytest
from _pytest.fixtures import SubRequest
from cluster_helpers import wait_for_dcos_oss
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from docker.models.containers import Container


cryptography_default_backend = cryptography.hazmat.backends.default_backend()


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


@pytest.fixture()
def rsa_keypair() -> Tuple[str, str]:
    """
    Generate an RSA keypair with a key size of 2048 bits and an
    exponent of 65537. Serialize the public key in the the
    X.509 SubjectPublicKeyInfo/OpenSSL PEM public key format
    (RFC 5280). Serialize the private key in the PKCS#8 (RFC 3447)
    format.

    Returns:
        (private key, public key) 2-tuple, both unicode
        objects holding the serialized keys.
    """

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=cryptography_default_backend,
    )
    privkey_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = private_key.public_key()
    pubkey_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return privkey_pem.decode('ascii'), pubkey_pem.decode('ascii')


@pytest.fixture()
def jwt_token() -> Callable[[str, str, int], str]:
    def _token(uid: str, private_key: str, exp: int) -> str:
        return jwt.encode(
            {'uid': uid, 'exp': time.time() + exp},
            private_key,
            algorithm='RS256',
        ).decode('ascii')

    return _token


@pytest.fixture
def static_three_master_cluster(
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


@pytest.fixture
def zookeeper_backend() -> Generator[Container, None, None]:
    """
    Create a ZooKeeper backend container to support a dynamic DC/OS cluster
    setup.
    """
    ts = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    client = docker.from_env(version='auto')
    zookeeper = client.containers.run(
        image='digitalwonderland/zookeeper',
        name='zk-backend-{}'.format(ts),
        environment={'ZOOKEEPER_TICK_TIME': 100},
        detach=True,
    )
    zookeeper.reload()
    try:
        yield zookeeper
    finally:
        zookeeper.remove(force=True)


@pytest.fixture
def dynamic_three_master_cluster(
    artifact_path: Path,
    docker_backend: Docker,
    zookeeper_backend: Container,
    request: SubRequest,
    log_dir: Path,
) -> Generator[Cluster, None, None]:
    """Spin up a dynamic DC/OS cluster with three master nodes."""
    exhibitor_zk_port = 2181
    exhibitor_zk_ip_address = zookeeper_backend.attrs['NetworkSettings']['IPAddress']
    exhibitor_zk_host = '{ip_address}:{port}'.format(
        ip_address=exhibitor_zk_ip_address,
        port=exhibitor_zk_port,
    )
    dynamic_ee_config = {
        'exhibitor_storage_backend': 'zookeeper',
        'exhibitor_zk_hosts': exhibitor_zk_host,
        'exhibitor_zk_path': '/zk-example',
        'master_discovery': 'master_http_loadbalancer',
        # `exhibitor_address` is required for a `zookeeper` based cluster, but
        # does not need to be valid because the cluster has no agents.
        'exhibitor_address': 'none',
        'num_masters': '3',
    }

    with Cluster(
        cluster_backend=docker_backend,
        masters=3,
        agents=0,
        public_agents=0,
    ) as cluster:
        dcos_config = {
            **cluster.base_config,
            **dynamic_ee_config,
        }
        dcos_config.pop('master_list')
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
