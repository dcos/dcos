import copy
import os
import tempfile

import pytest

import ssh.validate


@pytest.fixture
def default_config():
    return copy.deepcopy({
        'agent_list': ['127.0.0.1', '127.0.0.2'],
        'master_list': ['10.10.0.1', '10.10.0.2'],
        'ssh_port': 22,
        'ssh_user': 'centos',
    })


def test_validate_config(default_config):
    with tempfile.NamedTemporaryFile(mode='+r') as tmp:
        default_config['ssh_key_path'] = tmp.name
        assert ssh.validate.validate_config(default_config) == {}


def test_validate_config_not_encrypted(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        with open(tmp.name, 'w') as fh:
            fh.write('ENCRYPTED')

        assert ssh.validate.validate_config(default_config) == {
            'ssh_key_path': ('Encrypted SSH keys (which contain passphrases) are not allowed. Use a key without a '
                             'passphrase.')
        }


def test_config_permissions(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        os.chmod(tmp.name, 777)
        assert ssh.validate.validate_config(default_config) == {
            'ssh_key_path': ('ssh_key_path must be only read / write / executable by the owner. It may not be read / '
                             'write / executable by group, or other.')
        }


def test_agent_list_ipv4(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        default_config['agent_list'] = ['127.0.0.1', '127.0.0.2', 'foo']
        assert ssh.validate.validate_config(default_config) == {
            'agent_list': 'Only IPv4 values are allowed. The following are invalid IPv4 addresses: [\'foo\']'
        }


def test_agent_list_dups(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        default_config['agent_list'] = ['127.0.0.1', '127.0.0.2', '127.0.0.1']
        assert ssh.validate.validate_config(default_config) == {
            'agent_list': 'List cannot contain duplicates: 127.0.0.1'}


def test_master_agent_list_dups(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        default_config['master_list'] = ['10.10.0.1', '10.10.0.2', '127.0.0.2']
        assert ssh.validate.validate_config(default_config) == {
            'master_list': 'master_list and agent_list cannot contain duplicates 127.0.0.2'
        }


def test_ssh_user(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        default_config['ssh_user'] = 123
        assert ssh.validate.validate_config(default_config) == {'ssh_user': 'ssh_user must be a string'}


def test_ssh_port(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        default_config['ssh_port'] = 100000
        assert ssh.validate.validate_config(default_config) == {'ssh_port': 'ssh port should be int between 1 - 32000'}


def test_public_agent_list(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        default_config['public_agent_list'] = ['10.10.0.1']
        default_config['agent_list'] = ['10.10.0.1']
        assert ssh.validate.validate_config(default_config) == {
            'agent_list': 'master_list and agent_list cannot contain duplicates 10.10.0.1',
            'public_agent_list': 'master_list and agent_list cannot contain duplicates 10.10.0.1',
            'master_list': 'master_list and agent_list cannot contain duplicates 10.10.0.1'}
