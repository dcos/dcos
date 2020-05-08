import uuid

import cryptography.hazmat.backends
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from gen.tests.utils import validate_error, validate_error_multikey, validate_success


cryptography_default_backend = cryptography.hazmat.backends.default_backend()


def generate_rsa_public_key():
    """
    Generate an RSA keypair with a key size of 2048 bits and an
    exponent of 65537. Serialize the public key in the the
    X.509 SubjectPublicKeyInfo/OpenSSL PEM public key format
    (RFC 5280).
    Returns:
        public key as unicode objects holding the serialized key.
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=cryptography_default_backend,
    )
    public_key = private_key.public_key()
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('ascii')


class TestSuperuserServiceAccountCredentials:
    """
    Tests superuser service account credential parsing.
    """

    def test_uid_and_public_key_not_provided(self):
        """
        No error is shown if ``superuser_service_account_uid`` and
        ``superuser_service_account_public_key`` are not provided.
        """
        validate_success(new_arguments={})

    def test_uid_and_public_key_provided(self):
        """
        No error is shown if valid ``superuser_service_account_uid`` and
        ``superuser_service_account_public_key`` are provided.
        """
        validate_success(
            new_arguments={
                'superuser_service_account_uid': str(uuid.uuid4()),
                'superuser_service_account_public_key': generate_rsa_public_key(),
            }
        )

    def test_uid_not_provided(self):
        """
        An error is shown when ``superuser_service_account_public_key`` is
        provided but ``superuser_service_account_uid`` is not.
        """
        validate_error_multikey(
            new_arguments={
                'superuser_service_account_public_key': generate_rsa_public_key(),
            },
            keys=[
                'superuser_service_account_uid',
                'superuser_service_account_public_key',
            ],
            message=(
                "'superuser_service_account_uid' and "
                "'superuser_service_account_public_key' "
                "must both be empty or both be non-empty"
            )
        )

    def test_public_key_not_provided(self):
        """
        An error is shown when ``superuser_service_account_uid`` is
        provided but ``superuser_service_account_public_key`` is not.
        """
        validate_error_multikey(
            new_arguments={'superuser_service_account_uid': str(uuid.uuid4())},
            keys=[
                'superuser_service_account_uid',
                'superuser_service_account_public_key',
            ],
            message=(
                "'superuser_service_account_uid' and "
                "'superuser_service_account_public_key' "
                "must both be empty or both be non-empty"
            )
        )

    def test_provided_uid_empty(self):
        """
        An error is shown when an empty ``superuser_service_account_uid``
        is together with a valid ``superuser_service_account_public_key``.
        """
        validate_error_multikey(
            new_arguments={
                'superuser_service_account_uid': '',
                'superuser_service_account_public_key': generate_rsa_public_key(),
            },
            keys=[
                'superuser_service_account_uid',
                'superuser_service_account_public_key',
            ],
            message=(
                "'superuser_service_account_uid' and "
                "'superuser_service_account_public_key' "
                "must both be empty or both be non-empty"
            )
        )

    def test_provided_public_key_invalid(self):
        """
        An error is shown when ``superuser_service_account_public_key`` is
        given a value which is not an RSA public key encoded in the OpenSSL PEM
        format.
        """
        validate_error(
            new_arguments={
                'superuser_service_account_uid': str(uuid.uuid4()),
                'superuser_service_account_public_key': str(uuid.uuid4()),
            },
            key='_superuser_service_account_public_key_json',
            message=(
                'superuser_service_account_public_key has an invalid value. It '
                'must hold an RSA public key encoded in the OpenSSL PEM '
                'format. Error: Could not deserialize key data.'
            )
        )
