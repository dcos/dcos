"""
A collection of tests covering basic IAM functionality in DC/OS.

Assume that access control is activated in Master Admin Router (could be
disabled with `oauth_enabled`) and therefore authenticate individual HTTP
requests by using dcos_api_session.
"""
import json
import logging
import time
import uuid

from typing import Any

import cryptography.hazmat.backends
import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dcos_test_utils.dcos_api import DcosApiSession
from jwt.utils import base64url_decode


__maintainer__ = 'jgehrcke'
__contact__ = 'security-team@mesosphere.io'


log = logging.getLogger(__name__)


def _generate_rsa_keypair() -> Any:
    """
    Generate an RSA keypair. Serialize the public key in the the X.509
    SubjectPublicKeyInfo/OpenSSL PEM public key format (RFC 5280). Serialize the
    private key in the PKCS#8 (RFC 3447) format.

    Returns:
        (private key, public key) 2-tuple, both unicode
        objects holding the serialized keys.
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=cryptography.hazmat.backends.default_backend())

    privkey_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())

    public_key = private_key.public_key()
    pubkey_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)

    return privkey_pem.decode('ascii'), pubkey_pem.decode('ascii')


default_rsa_privkey, default_rsa_pubkey = _generate_rsa_keypair()


def test_service_account_create_login_delete(dcos_api_session: DcosApiSession, noauth_api_session: DcosApiSession
                                             ) -> None:

    # Create service user account, share the public key with the IAM.
    serviceuid = 'testservice'
    r = dcos_api_session.put(
        '/acs/api/v1/users/' + serviceuid,
        json={'description': 'foo', 'public_key': default_rsa_pubkey}
    )
    assert r.status_code == 201, r.text

    # Generate short-lived service login token (RS256 JWT signed with
    # the service's private key).
    service_login_token = jwt.encode(
        {'uid': serviceuid, 'exp': time.time() + 30},
        default_rsa_privkey,
        algorithm='RS256'
    ).decode('ascii')

    # Log in via the service login token.
    r = noauth_api_session.post(
        '/acs/api/v1/auth/login',
        json={'uid': serviceuid, 'token': service_login_token}
    )
    assert r.status_code == 200, r.text

    # Confirm that the response body contains a DC/OS authentication token.
    token = r.json()['token']
    header_bytes, payload_bytes, signature_bytes = [
        base64url_decode(_.encode('ascii')) for _ in token.split(".")]

    header_dict = json.loads(header_bytes.decode('ascii'))
    assert header_dict['alg'] == 'RS256'
    assert header_dict['typ'] == 'JWT'

    payload_dict = json.loads(payload_bytes.decode('ascii'))
    assert 'exp' in payload_dict
    assert 'uid' in payload_dict
    assert payload_dict['uid'] == serviceuid

    # Verify that the service user account appears in the users collection.
    r = dcos_api_session.get('/acs/api/v1/users', query='type=service')
    uids = [o['uid'] for o in r.json()['array']]
    assert serviceuid in uids

    # Delete the service user account.
    r = dcos_api_session.delete('/acs/api/v1/users/' + serviceuid)
    assert r.status_code == 204

    # Confirm that service does not appear in collection anymore.
    r = dcos_api_session.get('/acs/api/v1/users', query='type=service')
    uids = [o['uid'] for o in r.json()['array']]
    assert serviceuid not in uids


def test_user_account_create_login_delete(dcos_api_session: DcosApiSession, noauth_api_session: DcosApiSession) -> None:

    uid = str(uuid.uuid4())
    password = str(uuid.uuid4())

    r = dcos_api_session.put(
        '/acs/api/v1/users/' + uid,
        json={'description': str(uuid.uuid4()), 'password': password},
    )
    assert r.status_code == 201

    r = noauth_api_session.post(
        '/acs/api/v1/auth/login',
        json={'uid': uid, 'password': password},
    )
    assert r.status_code == 200
    assert 'token' in r.json()

    dcos_url = str(dcos_api_session.default_url)
    r = requests.get(
        dcos_url + '/pkgpanda/active.buildinfo.full.json',
        headers={'Authorization': 'token=' + r.json()['token']}
    )
    assert r.status_code == 200

    r = dcos_api_session.get('/acs/api/v1/users/')
    uids = [o['uid'] for o in r.json()['array']]
    assert uid in uids

    r = dcos_api_session.delete('/acs/api/v1/users/' + uid)
    assert r.status_code == 204

    r = dcos_api_session.get('/acs/api/v1/users/')
    uids = [o['uid'] for o in r.json()['array']]
    assert uid not in uids
