# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""This module provides a set tools for generating JSON Web Tokens

    Attributes:
        AUTHTOKEN_LIFETIME_SECONDS (int): default token validity period, measured from
            time.time(), expressed in seconds
"""

import jwt
import logging
import time

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

log = logging.getLogger(__name__)

AUTHTOKEN_LIFETIME_SECONDS = 3600


def load_key(key_path):
    """Load a key from a file

    `ascii` encoding is assumed as the key will be either RSA PEM, or base64
    encoded shared secret. The contents are stripped.

    Args:
        key_path (str): path to the file that contains the key

    Returns:
        The contents of the file in `key_path` path

    Raises:
        OSError: problem occured while loading the file
    """
    try:
        with open(key_path, 'r', encoding='ascii') as fh:
            key_data = fh.read().strip()
    except OSError:
        log.exception('Cannot read key file `%s`', key_path)
        raise

    return key_data


def decode_pem_key(key_pem):
    """Convert plaintext PEM key into the format usable for JWT generation

    Args:
        key_pam (str): key data in PEM format, presented as plain string

    Returns:
        Parsed PEM data
    """
    private_key = serialization.load_pem_private_key(
        data=key_pem.encode('ascii'),
        password=None,
        backend=default_backend())

    msg = 'Unexpected private key type'
    assert isinstance(private_key, rsa.RSAPrivateKey), msg
    assert private_key.key_size >= 2048, 'RSA key size too small'

    return private_key


def generate_rs256_jwt(
        key_path, uid, exp=None, skip_uid_claim=False, skip_exp_claim=False):
    """Generate a RS256 JSON Web Token

    Args:
        key_path (str): path to the private key encoded in PEM format, which will be
            used for token signing/encoding
        uid (str): a value of `uid` JWT claim that should be set in the token
        exp (int): a value of `exp` JWT claim that should be set in the token,
            by default it's AUTHTOKEN_LIFETIME_SECONDS seconds from now.
        skip_uid_claim (bool): specifies whether the UID claim should be present
            in the token
        skip_exp_claim (bool): specifies whether the `exp` claim should be present
            in the token

    Returns:
        A JSON Web Token string that can be used directly in HTTP headers/cookies/etc...
    """
    if exp is None:
        exp = time.time() + AUTHTOKEN_LIFETIME_SECONDS

    payload = {"uid": uid,
               "exp": int(exp)}
    if skip_uid_claim:
        del payload['uid']

    if skip_exp_claim:
        del payload['exp']


    key_pem = load_key(key_path)

    key = decode_pem_key(key_pem)

    jwt_token = jwt.encode(payload, key, algorithm='RS256').decode('ascii')

    return jwt_token


def generate_hs256_jwt(
        key_path, uid, exp=None, skip_uid_claim=False, skip_exp_claim=False):
    """Generate a HS256 JSON Web Token

    Args:
        key_path (str): path to shared secret, which will be used for token
            signing/encoding
        uid (str): a value of `uid` JWT claim that should be set in the token
        exp (int): a value of `exp` JWT claim that should be set in the token,
            by default it's AUTHTOKEN_LIFETIME_SECONDS seconds from now.
        skip_uid_claim (bool): specifies whether the `uid` claim should be present
            in the token
        skip_exp_claim (bool): specifies whether the `exp` claim should be present
            in the token

    Returns:
        A JSON Web Token string that can be used directly in HTTP headers/cookies/etc...
    """
    if exp is None:
        exp = time.time() + AUTHTOKEN_LIFETIME_SECONDS

    payload = {"uid": uid,
               "exp": int(exp)}
    if skip_uid_claim:
        del payload['uid']

    if skip_exp_claim:
        del payload['exp']

    key = load_key(key_path)

    jwt_token = jwt.encode(payload, key, algorithm='HS256').decode('ascii')

    return jwt_token
