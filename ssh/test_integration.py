import asyncio
import getpass
import json
import os
import random
import socket
import subprocess
import time
import uuid
from contextlib import contextmanager

import pytest
from retrying import retry

import pkgpanda.util
from ssh.runner import MultiRunner, Node
from ssh.utils import AbstractSSHLibDelegate, CommandChain


def can_connect(port):
    sock = socket.socket()
    sock.settimeout(0.1)  # Always localhost, should be wayy faster than this.
    try:
        sock.connect(('127.0.0.1', port))
        return True
    except OSError:
        return False


class SshdManager():
    def __init__(self, tmpdir):
        self.tmpdir = tmpdir
        self.sshd_config_path = str(tmpdir.join('sshd_config'))
        self.key_path = str(tmpdir.join('host_key'))
        subprocess.check_call(['ssh-keygen', '-f', self.key_path, '-t', 'rsa', '-N', ''])
        self.key = pkgpanda.util.load_string(self.key_path)

        config = [
            'Protocol 1,2',
            'RSAAuthentication yes',
            'PubkeyAuthentication yes',
            'StrictModes no',
            'LogLevel DEBUG']
        config.append('AuthorizedKeysFile {}'.format(tmpdir.join('host_key.pub')))
        config.append('HostKey {}'.format(self.key_path))

        with open(self.sshd_config_path, 'w') as f:
            f.write('\n'.join(config))

        assert tmpdir.join('host_key').check()
        assert tmpdir.join('host_key.pub').check()
        assert tmpdir.join('sshd_config').check()

    @contextmanager
    def run(self, count):
        # Get unique number of available TCP ports on the system
        sshd_ports = []
        for try_port in random.sample(range(10000, 11000), count):
            # If the port is already in use, skip it.
            while can_connect(try_port):
                try_port += 1
            sshd_ports.append(try_port)

        # Run sshd servers in parallel, cleaning up when the yield returns.
        subprocesses = []
        for port in sshd_ports:
            subprocesses.append(subprocess.Popen(
                ['/usr/sbin/sshd', '-p{}'.format(port), '-f{}'.format(self.sshd_config_path), '-e', '-D'],
                cwd=str(self.tmpdir)))

        # Wait for the ssh servers to come up
        @retry(stop_max_delay=1000, retry_on_result=lambda x: x is False)
        def check_server(port):
            return can_connect(port)

        for port in sshd_ports:
            check_server(port)

        yield sshd_ports

        # Stop all the subproceses. They are ephemeral temporary SSH connections, no point in being nice
        # with SIGTERM.
        for s in subprocesses:
            s.kill()


@pytest.fixture
def sshd_manager(tmpdir):
    return SshdManager(tmpdir)


@pytest.yield_fixture
def loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_ssh_async(sshd_manager, loop):
    class DummyAsyncDelegate(AbstractSSHLibDelegate):
        def on_update(self, future, callback):
            callback.set_result(True)

        def on_done(self, *args, **kwargs):
            pass

        def prepare_status(self, name, nodes):
            pass

    with sshd_manager.run(20) as sshd_ports:
        runner = MultiRunner(['127.0.0.1:{}'.format(port) for port in sshd_ports], user=getpass.getuser(),
                             key_path=sshd_manager.key_path, async_delegate=DummyAsyncDelegate())
        host_port = ['127.0.0.1:{}'.format(port) for port in sshd_ports]

        chain = CommandChain('test')
        chain.add_execute(['uname', '-a'])
        try:
            results = loop.run_until_complete(runner.run_commands_chain_async([chain], block=True))
        finally:
            loop.close()

        assert not os.path.isfile('test.json')
        assert len(results) == 20
        for host_result in results:
            for command_result in host_result:
                for host, process_result in command_result.items():
                    assert process_result['returncode'] == 0, process_result['stderr']
                    assert host in host_port
                    assert '/usr/bin/ssh' in process_result['cmd']
                    assert 'uname' in process_result['cmd']
                    assert '-tt' in process_result['cmd']
                    assert len(process_result['cmd']) == 13


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_scp_remote_to_local_async(sshd_manager, loop):

    with sshd_manager.run(1) as sshd_ports:
        workspace = str(sshd_manager.tmpdir)
        id = uuid.uuid4().hex
        pkgpanda.util.write_string(workspace + '/pilot.txt', id)
        runner = MultiRunner(['127.0.0.1:{}'.format(port) for port in sshd_ports], user=getpass.getuser(),
                             key_path=sshd_manager.key_path)
        host_port = ['127.0.0.1:{}'.format(port) for port in sshd_ports]

        chain = CommandChain('test')
        chain.add_copy(workspace + '/pilot.txt.copied', workspace + '/pilot.txt', remote_to_local=True)
        try:
            copy_results = loop.run_until_complete(runner.run_commands_chain_async([chain], block=True,
                                                                                   state_json_dir=workspace))
        finally:
            loop.close()

        assert len(copy_results) == 1
        assert os.path.isfile(workspace + '/pilot.txt.copied')
        assert pkgpanda.util.load_string(workspace + '/pilot.txt.copied') == id
        for host_result in copy_results:
            for command_result in host_result:
                for host, process_result in command_result.items():
                    assert process_result['returncode'] == 0, process_result['stderr']
                    assert host in host_port
                    assert '/usr/bin/scp' in process_result['cmd']
                    assert workspace + '/pilot.txt.copied' in process_result['cmd']
                    assert '-tt' not in process_result['cmd']


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_scp_async(sshd_manager, loop):
    with sshd_manager.run(1) as sshd_ports:
        workspace = str(sshd_manager.tmpdir)
        id = uuid.uuid4().hex
        pkgpanda.util.write_string(workspace + '/pilot.txt', id)
        runner = MultiRunner(['127.0.0.1:{}'.format(port) for port in sshd_ports], user=getpass.getuser(),
                             key_path=sshd_manager.key_path)
        host_port = ['127.0.0.1:{}'.format(port) for port in sshd_ports]

        chain = CommandChain('test')
        chain.add_copy(workspace + '/pilot.txt', workspace + '/pilot.txt.copied')
        try:
            copy_results = loop.run_until_complete(runner.run_commands_chain_async([chain], block=True,
                                                                                   state_json_dir=workspace))
        finally:
            loop.close()

        assert len(copy_results) == 1
        assert os.path.isfile(workspace + '/pilot.txt.copied')
        assert pkgpanda.util.load_string(workspace + '/pilot.txt.copied') == id
        for host_result in copy_results:
            for command_result in host_result:
                for host, process_result in command_result.items():
                    assert process_result['returncode'] == 0, process_result['stderr']
                    assert host in host_port
                    assert '/usr/bin/scp' in process_result['cmd']
                    assert workspace + '/pilot.txt' in process_result['cmd']


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_scp_recursive_async(sshd_manager, loop):
    with sshd_manager.run(1) as sshd_ports:
        workspace = str(sshd_manager.tmpdir)

        id = uuid.uuid4().hex
        pkgpanda.util.write_string(workspace + '/recursive_pilot.txt', id)
        runner = MultiRunner(['127.0.0.1:{}'.format(port) for port in sshd_ports], user=getpass.getuser(),
                             key_path=sshd_manager.key_path)
        host_port = ['127.0.0.1:{}'.format(port) for port in sshd_ports]

        chain = CommandChain('test')
        chain.add_copy(workspace + '/recursive_pilot.txt', workspace + '/recursive_pilot.txt.copied', recursive=True)
        try:
            copy_results = loop.run_until_complete(runner.run_commands_chain_async([chain], block=True,
                                                                                   state_json_dir=workspace))
        finally:
            loop.close()

        dest_path = workspace + '/recursive_pilot.txt.copied'
        assert os.path.exists(dest_path)
        assert os.path.isfile(dest_path)
        assert len(copy_results) == 1
        assert pkgpanda.util.load_string(dest_path) == id
        for host_result in copy_results:
            for command_result in host_result:
                for host, process_result in command_result.items():
                    assert process_result['returncode'] == 0, process_result['stderr']
                    assert host in host_port
                    assert '/usr/bin/scp' in process_result['cmd']
                    assert '-r' in process_result['cmd']
                    assert workspace + '/recursive_pilot.txt' in process_result['cmd']


def test_command_chain():
    chain = CommandChain('test')
    chain.add_execute(['cmd2'])
    chain.add_copy('/local', '/remote')
    chain.prepend_command(['cmd1'])
    chain.add_execute(['cmd3'])

    assert chain.get_commands() == [
        ('execute', ['cmd1'], None, None),
        ('execute', ['cmd2'], None, None),
        ('copy', '/local', '/remote', False, False, None),
        ('execute', ['cmd3'], None, None)
    ]


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_ssh_command_terminate_async(sshd_manager, loop):
    with sshd_manager.run(1) as sshd_ports:
        workspace = str(sshd_manager.tmpdir)

        runner = MultiRunner(['127.0.0.1:{}'.format(port) for port in sshd_ports], user=getpass.getuser(),
                             key_path=sshd_manager.key_path, process_timeout=0.05)

        chain = CommandChain('test')
        chain.add_execute(['sleep', '20'])
        start_time = time.time()
        try:
            results = loop.run_until_complete(runner.run_commands_chain_async([chain], block=True,
                                                                              state_json_dir=workspace))
        finally:
            loop.close()
        elapsed_time = time.time() - start_time
        assert elapsed_time < 5
        assert os.path.isfile(workspace + '/test.json')

        with open(workspace + '/test.json') as fh:
            result_json = json.load(fh)
            assert result_json['total_hosts'] == 1
            assert 'hosts_failed' not in result_json
            assert 'hosts_success' not in result_json

        for host_result in results:
            for command_result in host_result:
                for host, process_result in command_result.items():
                    assert result_json['hosts'][host]['host_status'] == 'terminated'
                    assert process_result['stdout'] == ['']
                    assert process_result['stderr'] == ['']
                    assert process_result['returncode'] is None


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not support ssh native")
def test_tags_async(sshd_manager, loop):
    with sshd_manager.run(1) as sshd_ports:
        workspace = str(sshd_manager.tmpdir)
        host_ports = ['127.0.0.1:{}'.format(port) for port in sshd_ports]

        targets = []
        for _port in sshd_ports:
            _host = Node('127.0.0.1:{}'.format(_port), {'tag1': 'test1', 'tag2': 'test2'})
            targets.append(_host)
        runner = MultiRunner(targets, user=getpass.getuser(),
                             key_path=workspace + '/host_key')

        chain = CommandChain('test')
        chain.add_execute(['sleep', '1'])
        try:
            loop.run_until_complete(runner.run_commands_chain_async([chain], block=True, state_json_dir=workspace))
        finally:
            loop.close()

        with open(workspace + '/test.json') as fh:
            result_json = json.load(fh)
            for host_port in host_ports:
                assert 'tags' in result_json['hosts'][host_port]
                assert len(result_json['hosts'][host_port]['tags']) == 2
                assert result_json['hosts'][host_port]['tags']['tag1'] == 'test1'
                assert result_json['hosts'][host_port]['tags']['tag2'] == 'test2'
                assert result_json['hosts'][host_port]['commands'][0]['cmd'] == [
                    "/usr/bin/ssh",
                    "-oConnectTimeout=10",
                    "-oStrictHostKeyChecking=no",
                    "-oUserKnownHostsFile=/dev/null",
                    "-oBatchMode=yes",
                    "-oPasswordAuthentication=no",
                    "-p{}".format(sshd_ports[0]),
                    "-i",
                    "{}/host_key".format(workspace),
                    "-tt",
                    "{}@127.0.0.1".format(getpass.getuser()),
                    "sleep",
                    "1"
                ]
