import time
import uuid
from pathlib import Path
from typing import Tuple

import cryptography.hazmat.backends
import jwt
import requests
from _pytest.fixtures import SubRequest
from cluster_helpers import (
    wait_for_dcos_oss,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dcos_e2e.base_classes import ClusterBackend
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Output


cryptography_default_backend = cryptography.hazmat.backends.default_backend()


def generate_rsa_keypair() -> Tuple[str, str]:
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


def test_superuser_service_account_login(
    docker_backend: ClusterBackend,
    artifact_path: Path,
    request: SubRequest,
    log_dir: Path,
) -> None:
    """
    Tests for successful superuser service account login which asserts
    that the default user has been created during cluster start.
    """
    superuser_uid = str(uuid.uuid4())
    superuser_private_key, superuser_public_key = generate_rsa_keypair()
    config = {
        'superuser_service_account_uid': superuser_uid,
        'superuser_service_account_public_key': superuser_public_key,
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

        service_login_token = jwt.encode(
            {'uid': superuser_uid, 'exp': time.time() + 30},
            superuser_private_key,
            algorithm='RS256'
        ).decode('ascii')

        response = requests.post(
            login_endpoint,
            json={'uid': superuser_uid, 'token': service_login_token}
        )
        assert response.status_code == 200
