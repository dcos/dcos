"""
Surrogate conftest.py contents loaded by the conftest.py file.
"""
import logging
import os
import time
from pathlib import Path
from typing import Callable, Tuple

import cryptography.hazmat.backends
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dcos_e2e.backends import Docker


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
