import copy
import os
import tempfile

import pytest

import pkgpanda.util
import ssh.validate


@pytest.fixture
def default_config():
    return copy.deepcopy({
        'agent_list': ['127.0.0.1', '127.0.0.2'],
        'master_list': ['10.10.0.1', '10.10.0.2'],
        'ssh_port': 22,
        'ssh_user': 'centos',
    })


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_validate_config(default_config):
    with tempfile.NamedTemporaryFile(mode='+r') as tmp:
        default_config['ssh_key_path'] = tmp.name
        assert ssh.validate.validate_config(default_config) == {}


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_validate_config_not_encrypted(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        with open(tmp.name, 'w') as fh:
            fh.write('ENCRYPTED')

        assert ssh.validate.validate_config(default_config) == {
            'ssh_key_path': ('Encrypted SSH keys (which contain passphrases) are not allowed. Use a key without a '
                             'passphrase.')
        }


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_config_permissions(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        os.chmod(tmp.name, 777)
        assert ssh.validate.validate_config(default_config) == {
            'ssh_key_path': ('ssh_key_path must be only read / write / executable by the owner. It may not be read / '
                             'write / executable by group, or other.')
        }


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_agent_list_ipv4(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        default_config['agent_list'] = ['127.0.0.1', '127.0.0.2', 'foo']
        assert ssh.validate.validate_config(default_config) == {
            'agent_list': 'Invalid IPv4 addresses in list: foo'
        }


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_agent_list_dups(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        default_config['agent_list'] = ['127.0.0.1', '127.0.0.2', '127.0.0.1']
        assert ssh.validate.validate_config(default_config) == {
            'agent_list': 'List cannot contain duplicates: 127.0.0.1 appears 2 times'}


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_master_agent_list_dups(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        default_config['master_list'] = ['10.10.0.1', '10.10.0.2', '127.0.0.2']
        assert ssh.validate.validate_config(default_config) == {
            'master_list': 'master_list and agent_list cannot contain duplicates 127.0.0.2',
            'agent_list': 'master_list and agent_list cannot contain duplicates 127.0.0.2'
        }


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_ssh_port(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        default_config['ssh_port'] = 100000
        assert ssh.validate.validate_config(default_config) == \
            {'ssh_port': 'Must be between 1 and 32000 inclusive'}


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_public_agent_list(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name
        default_config['public_agent_list'] = ['10.10.0.1']
        default_config['agent_list'] = ['10.10.0.1']
        assert ssh.validate.validate_config(default_config) == {
            'agent_list': 'master_list and agent_list cannot contain duplicates 10.10.0.1',
            'public_agent_list': 'master_list and agent_list cannot contain duplicates 10.10.0.1',
            'master_list': 'master_list and agent_list cannot contain duplicates 10.10.0.1'}


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_ssh_parallelism(default_config):
    with tempfile.NamedTemporaryFile() as tmp:
        default_config['ssh_key_path'] = tmp.name

        # test ssh_parallelism range, should be ok within 1.100
        default_config['ssh_parallelism'] = 101
        assert ssh.validate.validate_config(default_config) == {
            'ssh_parallelism': 'Must be between 1 and 100 inclusive'}

        default_config['ssh_parallelism'] = 0
        assert ssh.validate.validate_config(default_config) == {
            'ssh_parallelism': 'Must be between 1 and 100 inclusive'}

        default_config['ssh_parallelism'] = 20
        assert ssh.validate.validate_config(default_config) == {}

        # ssh_parallelism must be integer
        default_config['ssh_parallelism'] = 'foo'
        assert ssh.validate.validate_config(default_config) == {
            'ssh_parallelism': 'Must be an integer but got a str: foo'}
