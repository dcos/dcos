import abc
import logging

import cryptography.hazmat.backends
import pkg_resources
import yaml
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

import pkgpanda

log = logging.getLogger(__name__)

MOCK_SSH_KEY_DATA = 'ssh_key_data'
MOCK_KEY_NAME = 'my_key_name'
MOCK_VPC_ID = 'vpc-foo-bar'
MOCK_SUBNET_ID = 'subnet-foo-bar'
MOCK_GATEWAY_ID = 'gateway-foo-bar'
MOCK_STACK_ID = 'this-is-a-important-test-stack::deadbeefdeadbeef'

NO_TEST_FLAG = 'NO PRIVATE SSH KEY PROVIDED - CANNOT TEST'


def check_testable(info):
    if info['ssh_private_key'] == NO_TEST_FLAG or 'ssh_user' not in info:
        raise LauncherError('MissingInput', 'DC/OS Launch is missing sufficient SSH info to run tests!')


def stub(output):
    def accept_any_args(*args, **kwargs):
        return output
    return accept_any_args


def get_temp_config_path(tmpdir, name, update: dict = None):
    config = pkgpanda.util.load_yaml(
        pkg_resources.resource_filename('launch', 'sample_configs/{}'.format(name)))
    if update is not None:
        config.update(update)
    new_config_path = tmpdir.join('my_config.yaml')
    new_config_path.write(yaml.dump(config))
    # sample configs specifically use ip-detect.sh for easy mocking
    tmpdir.join('ip-detect.sh').write(pkg_resources.resource_string('gen', 'ip-detect/aws.sh').decode())
    return str(new_config_path)


def check_keys(user_dict, key_list):
    missing = [k for k in key_list if k not in user_dict]
    if len(missing) > 0:
        raise LauncherError('MissingInput', 'The following keys were required but '
                            'not provided: {}'.format(repr(missing)))


class LauncherError(Exception):
    def __init__(self, error, msg):
        self.error = error
        self.msg = msg

    def __repr__(self):
        return '{}: {}'.format(self.error, self.msg if self.msg else self.__cause__)


class AbstractLauncher(metaclass=abc.ABCMeta):
    def create(self, config):
        raise NotImplementedError()

    def wait(self, info):
        raise NotImplementedError()

    def describe(self, info):
        raise NotImplementedError()

    def delete(self, info):
        raise NotImplementedError()

    def test(self, info, test_cmd):
        raise NotImplementedError()


def convert_host_list(host_list):
    """ Makes Host tuples more readable when using describe
    """
    return [{'private_ip': h.private_ip, 'public_ip': h.public_ip} for h in host_list]


def generate_RSA_keypair(key_size=2048):
    """Generate an RSA keypair.
    Create new RSA keypair with an exponent of 65537. Serialize the public
    key in the the X.509 SubjectPublicKeyInfo/OpenSSL PEM public key format
    (RFC 5280). Serialize the private key in the PKCS#8 (RFC 3447) format.
    Args:
        bits (int): the key length in bits.
    Returns:
        (private key, public key) 2-tuple, both unicode objects holding the
        serialized keys
    """
    crypto_backend = cryptography.hazmat.backends.default_backend()

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=crypto_backend)

    privkey_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())

    public_key = private_key.public_key()
    pubkey_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)

    return privkey_pem, pubkey_pem
