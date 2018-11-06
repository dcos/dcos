#!/usr/bin/env python

import argparse
import json
import logging
import os
import random
import shutil
import stat
import sys
import tempfile

import cryptography.hazmat.backends
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import base64url_decode, bytes_to_number

from dcos_internal_utils import bootstrap, exhibitor
from pkgpanda.actions import apply_service_configuration

log = logging.getLogger(__name__)


def check_root(fun):
    def wrapper(b, opts):
        if os.getuid() != 0:
            log.error('bootstrap must be run as root')
            sys.exit(1)
        fun(b, opts)
    return wrapper


@check_root
def dcos_adminrouter(b, opts):
    b.cluster_id('/var/lib/dcos/cluster-id')

    # Require the IAM to already be up and running. The IAM contains logic for
    # achieving consensus about a key pair, and exposes the public key
    # information via its JWKS endpoint. Talk directly to the local IAM instance
    # which is reachable via the local network interface.
    r = requests.get('http://127.0.0.1:8101/acs/api/v1/auth/jwks')

    if r.status_code != 200:
        log.info('JWKS retrieval failed. Got %s with body: %s', r, r.text)
        sys.exit(1)

    jwks = r.json()

    # For now plan with the first key in the JWKS to correspond to the current
    # private key used for signing authentiction tokens.
    key = jwks['keys'][0]

    exponent_bytes = base64url_decode(key['e'].encode('ascii'))
    exponent_int = bytes_to_number(exponent_bytes)
    modulus_bytes = base64url_decode(key['n'].encode('ascii'))
    modulus_int = bytes_to_number(modulus_bytes)
    # Generate a `cryptography` public key object instance from these numbers.
    public_numbers = rsa.RSAPublicNumbers(n=modulus_int, e=exponent_int)
    public_key = public_numbers.public_key(
        backend=cryptography.hazmat.backends.default_backend())

    # Serialize public key into the OpenSSL PEM public key format RFC 5280).
    pubkey_pem_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)

    os.makedirs('/run/dcos/dcos-adminrouter', exist_ok=True)
    pubkey_path = '/run/dcos/dcos-adminrouter/auth-token-verification-key'
    _write_file_bytes(pubkey_path, pubkey_pem_bytes, 0o644)
    shutil.chown(pubkey_path, user='dcos_adminrouter')


@check_root
def dcos_signal(b, opts):
    b.cluster_id('/var/lib/dcos/cluster-id')


@check_root
def dcos_telegraf_master(b, opts):
    b.cluster_id('/var/lib/dcos/cluster-id')


@check_root
def dcos_telegraf_agent(b, opts):
    b.cluster_id('/var/lib/dcos/cluster-id', readonly=True)


@check_root
def dcos_bouncer(b, opts):
    os.makedirs('/run/dcos/dcos-bouncer', exist_ok=True)
    shutil.chown('/run/dcos/dcos-bouncer', user='dcos_bouncer')


def noop(b, opts):
    return


bootstrappers = {
    'dcos-adminrouter': dcos_adminrouter,
    'dcos-bouncer': dcos_bouncer,
    'dcos-signal': dcos_signal,
    'dcos-diagnostics-master': noop,
    'dcos-diagnostics-agent': noop,
    'dcos-checks-master': noop,
    'dcos-checks-agent': noop,
    'dcos-marathon': noop,
    'dcos-mesos-master': noop,
    'dcos-mesos-slave': noop,
    'dcos-mesos-slave-public': noop,
    'dcos-cosmos': noop,
    'dcos-metronome': noop,
    'dcos-history': noop,
    'dcos-mesos-dns': noop,
    'dcos-net': noop,
    'dcos-telegraf-master': dcos_telegraf_master,
    'dcos-telegraf-agent': dcos_telegraf_agent,
}


def get_roles():
    return os.listdir('/opt/mesosphere/etc/roles')


def main():
    opts = parse_args()

    logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')
    log.setLevel(logging.DEBUG)

    log.info('Clearing proxy environment variables')
    for name in ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY']:
        os.environ.pop(name, None)
        os.environ.pop(name.lower(), None)

    if 'master' in get_roles():
        exhibitor.wait(opts.master_count)

    b = bootstrap.Bootstrapper(opts.zk)

    for service in opts.services:
        if service not in bootstrappers:
            log.error('Unknown service: {}'.format(service))
            sys.exit(1)
        apply_service_configuration(service)
        log.debug('bootstrapping {}'.format(service))
        bootstrappers[service](b, opts)


def get_zookeeper_address_agent():
    if os.getenv('MASTER_SOURCE') == 'master_list':
        # dcos-net agents with static master list
        with open('/opt/mesosphere/etc/master_list', 'r') as f:
            master_list = json.load(f)
        assert len(master_list) > 0
        return random.choice(master_list) + ':2181'
    elif os.getenv('EXHIBITOR_ADDRESS'):
        # dcos-net agents on AWS
        return os.getenv('EXHIBITOR_ADDRESS') + ':2181'
    else:
        # any other agent service
        return 'zk-1.zk:2181,zk-2.zk:2181,zk-3.zk:2181,zk-4.zk:2181,zk-5.zk:2181'


def get_zookeeper_address():
    # Masters use a special zk address since dcos-net and the like aren't up yet.
    roles = get_roles()
    if 'master' in roles:
        return '127.0.0.1:2181'

    if 'slave' in roles or 'slave_public' in roles:
        return get_zookeeper_address_agent()

    raise Exception("Can't get zookeeper address. Unknown role: {}".format(roles))


def parse_args():
    zk_default = get_zookeeper_address()

    parser = argparse.ArgumentParser()
    parser.add_argument('services', nargs='+')
    parser.add_argument(
        '--zk',
        type=str,
        default=zk_default,
        help='Host string passed to Kazoo client constructor.')
    parser.add_argument(
        '--master_count',
        type=str,
        default='/opt/mesosphere/etc/master_count',
        help='File with number of master servers')
    return parser.parse_args()


def _write_file_bytes(path, data, mode):
    """
    Open temporary file in target directory in 'w+b' mode and with locked-down
    file permissions. Write data (byte sequence) to temporary file. Once that
    has succeeded change the file permissions, and then create a hard link to
    the temporary file. This retains file permissions (hard link points to the
    same inode), and remains intact after automatic deletion of the temporary
    file (which happens upon context manager exit). Works on Linux and Windows.
    If `f.write(data)` fails the context manager cleans up.
    """
    assert isinstance(data, bytes)
    with tempfile.NamedTemporaryFile(dir=os.path.dirname(path)) as f:
        f.write(data)
        os.chmod(f.name, stat.S_IMODE(mode))
        try:
            os.remove(path)
        except OSError:
            pass
        os.link(f.name, path)
