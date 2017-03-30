import abc
import logging
import subprocess
import sys

import cryptography.hazmat.backends
import pkg_resources
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import pkgpanda
import ssh.ssher

log = logging.getLogger(__name__)

MOCK_SSH_KEY_DATA = 'ssh_key_data'
MOCK_KEY_NAME = 'my_key_name'
MOCK_VPC_ID = 'vpc-foo-bar'
MOCK_SUBNET_ID = 'subnet-foo-bar'
MOCK_GATEWAY_ID = 'gateway-foo-bar'
MOCK_STACK_ID = 'this-is-a-important-test-stack::deadbeefdeadbeef'

NO_TEST_FLAG = 'NO PRIVATE SSH KEY PROVIDED - CANNOT TEST'


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


class LauncherError(Exception):
    def __init__(self, error, msg):
        self.error = error
        self.msg = msg

    def __repr__(self):
        return '{}: {}'.format(self.error, self.msg if self.msg else self.__cause__)


class AbstractLauncher(metaclass=abc.ABCMeta):
    def get_ssher(self, info):
        return ssh.ssher.Ssher(info['ssh_user'], info['ssh_private_key'])

    def create(self, config):
        raise NotImplementedError()

    def wait(self, info):
        raise NotImplementedError()

    def describe(self, info):
        raise NotImplementedError()

    def delete(self, info):
        raise NotImplementedError()

    def test(self, info, args, env_dict, test_host=None, test_port=22):
        """
        Args:
            args: a list of args that will follow the py.test command
            env_dict: the env to use during the test
        """
        if args is None:
            args = list()
        if info['ssh_private_key'] == NO_TEST_FLAG or 'ssh_user' not in info:
            raise LauncherError('MissingInput', 'DC/OS Launch is missing sufficient SSH info to run tests!')
        details = self.describe(info)
        # populate minimal env if not already set
        if test_host is None:
            test_host = details['masters'][0]['public_ip']
        if 'MASTER_HOSTS' not in env_dict:
            env_dict['MASTER_HOSTS'] = ','.join(m['private_ip'] for m in details['masters'])
        if 'PUBLIC_MASTER_HOSTS' not in env_dict:
            env_dict['PUBLIC_MASTER_HOSTS'] = ','.join(m['private_ip'] for m in details['masters'])
        if 'SLAVE_HOSTS' not in env_dict:
            env_dict['SLAVE_HOSTS'] = ','.join(m['private_ip'] for m in details['private_agents'])
        if 'PUBLIC_SLAVE_HOSTS' not in env_dict:
            env_dict['PUBLIC_SLAVE_HOSTS'] = ','.join(m['private_ip'] for m in details['public_agents'])
        if 'DCOS_DNS_ADDRESS' not in env_dict:
            env_dict['DCOS_DNS_ADDRESS'] = 'http://' + details['masters'][0]['private_ip']
        env_string = ' '.join(['{}={}'.format(e, env_dict[e]) for e in env_dict])
        arg_string = ' '.join(args)
        pytest_cmd = """ "source /opt/mesosphere/environment.export &&
cd /opt/mesosphere/active/dcos-integration-test &&
{env} py.test {args}" """.format(env=env_string, args=arg_string)
        log.info('Running integration test...')
        return try_to_output_unbuffered(info, test_host, pytest_cmd)


def try_to_output_unbuffered(info, test_host, pytest_cmd):
    """ Writing straight to STDOUT buffer does not work with syscap so mock this function out
    """
    ssher = ssh.ssher.Ssher(info['ssh_user'], info['ssh_private_key'])
    try:
        ssher.command(test_host, ['bash', '-c', pytest_cmd], stdout=sys.stdout.buffer)
    except subprocess.CalledProcessError as e:
        log.exception('Test run failed!')
        return e.returncode
    return 0


def convert_host_list(host_list):
    """ Makes Host tuples more readable when using describe
    """
    return [{'private_ip': h.private_ip, 'public_ip': h.public_ip} for h in host_list]


def generate_rsa_keypair(key_size=2048):
    """Generate an RSA keypair.
    Create new RSA keypair with an exponent of 65537. Serialize the public
    key OpenSSH format that is used by providers for specifying access keys
    Serialize the private key in the PKCS#8 (RFC 3447) format.
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
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH)

    return privkey_pem, pubkey_pem
