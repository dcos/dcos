import asyncio
import copy
import logging
import os
try:
    import pty
except ImportError:
    pass
import sys

from contextlib import contextmanager

import ssh.validate
from pkgpanda.util import is_windows
from ssh.utils import CommandChain, JsonDelegate

if not is_windows:
    assert 'pty' in sys.modules

log = logging.getLogger(__name__)


@contextmanager
def make_slave_pty():
    master_pty, slave_pty = pty.openpty()
    yield slave_pty
    os.close(slave_pty)
    os.close(master_pty)


def parse_ip(ip: str, default_port: int):
    tmp = ip.split(':')
    if len(tmp) == 2:
        return {"ip": tmp[0], "port": int(tmp[1])}
    elif len(tmp) == 1:
        return {"ip": ip, "port": default_port}
    else:
        raise ValueError(
            "Expected a string of form <ip> or <ip>:<port> but found a string with more than one " +
            "colon in it. NOTE: IPv6 is not supported at this time. Got: {}".format(ip))


class Node():
    def __init__(self, host, tags: dict=dict(), default_port: int=22):
        self.tags = copy.copy(tags)
        self.host = parse_ip(host, default_port)
        self.ip = self.host['ip']
        self.port = self.host['port']

    def get_full_host(self):
        _host = self.host.copy()
        _host.update({'tags': self.tags})
        return _host

    def __repr__(self):
        return '{}:{} tags={}'.format(
            self.ip,
            self.port,
            ', '.join(['{}:{}'.format(k, v) for k, v in sorted(self.tags.items())]))


def add_host(target, default_port):
    if isinstance(target, Node):
        return target
    return Node(target, default_port=default_port)


class MultiRunner():
    def __init__(self, targets: list, async_delegate=None, user=None, key_path=None, extra_opts='',
                 process_timeout=120, parallelism=10, default_port=22):
        # TODO(cmaloney): accept an "ssh_config" object which generates an ssh
        # config file, then add a '-F' to that temporary config file rather than
        # manually building up / adding the arguments in _get_base_args which is
        # very error prone to get the formatting right. Should have just one
        # host section which applies to all hosts, sets things like "user".
        self.extra_opts = extra_opts
        self.process_timeout = process_timeout
        self.user = user
        self.key_path = key_path
        self.ssh_bin = '/usr/bin/ssh'
        self.scp_bin = '/usr/bin/scp'
        self.async_delegate = async_delegate
        self.__targets = []
        for target in targets:
            self.__targets.append(add_host(target, default_port))
        self.__parallelism = parallelism

    def _get_base_args(self, bin_name, host):
        # TODO(cmaloney): Switch to SSH config file, documented above. A single
        # user is always required.
        if bin_name == self.ssh_bin:
            port_option = '-p'
            add_opts = ['-tt']
            if self.extra_opts:
                add_opts.extend(self.extra_opts.split(' '))
        else:
            port_option = '-P'
            add_opts = []
        shared_opts = [
            bin_name,
            '-oConnectTimeout=10',
            '-oStrictHostKeyChecking=no',
            '-oUserKnownHostsFile=/dev/null',
            '-oBatchMode=yes',
            '-oPasswordAuthentication=no',
            '{}{}'.format(port_option, host.port),
            '-i', self.key_path]
        shared_opts.extend(add_opts)
        return shared_opts

    @asyncio.coroutine
    def run_cmd_return_dict_async(self, cmd, host, namespace, future, stage):
        with make_slave_pty() as slave_pty:
            process = yield from asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=slave_pty,
                env={'TERM': 'linux'})
            stdout = b''
            stderr = b''
            try:
                stdout, stderr = yield from asyncio.wait_for(process.communicate(), self.process_timeout)
            except asyncio.TimeoutError:
                try:
                    process.terminate()
                except ProcessLookupError:
                    log.info('process with pid {} not found'.format(process.pid))
                log.error('timeout of {} sec reached. PID {} killed'.format(self.process_timeout, process.pid))

        # For each possible line in stderr, match from the beginning of the line for the
        # the confusing warning: "Warning: Permanently added ...". If the warning exists,
        # remove it from the string.
        err_arry = stderr.decode().split('\r')
        stderr = bytes('\n'.join([line for line in err_arry if not line.startswith(
            'Warning: Permanently added')]), 'utf-8')

        process_output = {
            '{}:{}'.format(host.ip, host.port): {
                "cmd": cmd,
                "stdout": stdout.decode().split('\n'),
                "stderr": stderr.decode().split('\n'),
                "returncode": process.returncode,
                "pid": process.pid,
                "stage": stage
            }
        }

        future.set_result((namespace, process_output, host))
        return process_output

    @asyncio.coroutine
    def run_async(self, host, command, namespace, future, stage):
        # command consists of (command_flag, command, rollback, stage)
        # we will ignore all but command for now
        _, cmd, _, _ = command

        # we may lazy evaluate a command based on Node() class
        if callable(cmd):
            cmd = cmd(host)

        full_cmd = self._get_base_args(self.ssh_bin, host) + ['{}@{}'.format(self.user, host.ip)] + cmd
        log.debug('executing command {}'.format(full_cmd))
        result = yield from self.run_cmd_return_dict_async(full_cmd, host, namespace, future, stage)
        return result

    @asyncio.coroutine
    def copy_async(self, host, command, namespace, future, stage):
        # command[0] is command_flag, command[-1] is stage
        # we will ignore them here.
        _, local_path, remote_path, remote_to_local, recursive, _ = command
        copy_command = []
        if recursive:
            copy_command += ['-r']
        remote_full_path = '{}@{}:{}'.format(self.user, host.ip, remote_path)
        if remote_to_local:
            copy_command += [remote_full_path, local_path]
        else:
            copy_command += [local_path, remote_full_path]
        full_cmd = self._get_base_args(self.scp_bin, host) + copy_command
        log.debug('copy with command {}'.format(full_cmd))
        result = yield from self.run_cmd_return_dict_async(full_cmd, host, namespace, future, stage)
        return result

    def _run_chain_command(self, chain: CommandChain, host, chain_result):

        # Prepare status json
        if self.async_delegate is not None:
            log.debug('Preparing a status json')
            self.async_delegate.prepare_status(chain.namespace, self.__targets)

        host_status = 'hosts_success'
        host_port = '{}:{}'.format(host.ip, host.port)

        command_map = {
            CommandChain.execute_flag: self.run_async,
            CommandChain.copy_flag: self.copy_async
        }

        process_exit_code_map = {
            None: {
                'host_status': 'terminated',
                'host_status_count': 'hosts_terminated'
            },
            0: {
                'host_status': 'success',
                'host_status_count': 'hosts_success'
            },
            'failed': {
                'host_status': 'failed',
                'host_status_count': 'hosts_failed'
            }
        }
        for command in chain.get_commands():
            stage = command[-1]
            if stage is not None:
                # a stage can be a function which takes a Node() object and does evaluation
                if callable(stage):
                    stage = stage(host)
                log.debug('{}: {}'.format(host_port, stage))
            future = asyncio.Future()

            if self.async_delegate is not None:
                log.debug('Using async_delegate with callback')
                callback_called = asyncio.Future()
                future.add_done_callback(lambda future: self.async_delegate.on_update(future, callback_called))

            # command[0] is a type of a command, could be CommandChain.execute_flag, CommandChain.copy_flag
            result = yield from command_map.get(command[0], None)(host, command, chain.namespace, future, stage)
            status = process_exit_code_map.get(result[host_port]['returncode'], process_exit_code_map['failed'])
            host_status = status['host_status']

            if self.async_delegate is not None:
                # We need to make sure the callback was executed before we can proceed further
                # 5 seconds should be enough for a callback.
                try:
                    yield from asyncio.wait_for(callback_called, 5)
                except asyncio.TimeoutError:
                    log.error('Callback did not execute within 5 sec')
                    host_status = 'terminated'
                    break

            _, result, host_object = future.result()
            chain_result.append(result)
            if host_status != 'success':
                break

        if self.async_delegate is not None:
            # Update chain status.
            self.async_delegate.on_done(chain.namespace, result, host_status=host_status)

    @asyncio.coroutine
    def dispatch_chain(self, host, chains, sem):
        log.debug('Started dispatch_chain for host {}'.format(host))
        chain_result = []
        with (yield from sem):
            for chain in chains:
                yield from self._run_chain_command(chain, host, chain_result)
        return chain_result

    @asyncio.coroutine
    def run_commands_chain_async(self, chains: list, block=False, state_json_dir=None, delegate_extra_params={}):
        sem = asyncio.Semaphore(self.__parallelism)

        if state_json_dir:
            log.debug('Using default JsonDelegate method, state_json_dir {}'.format(state_json_dir))
            self.async_delegate = JsonDelegate(state_json_dir, len(self.__targets), **delegate_extra_params)
        else:
            assert self.async_delegate, 'async delegate must be set'

        if block:
            log.debug('Waiting for run_command_chain_async to execute')
            tasks = []
            for host in self.__targets:
                tasks.append(asyncio.async(self.dispatch_chain(host, chains, sem)))

            yield from asyncio.wait(tasks)
            log.debug('run_command_chain_async executed')
            return [task.result() for task in tasks]
        else:
            log.debug('Started run_command_chain_async in non-blocking mode')
            for host in self.__targets:
                asyncio.async(self.dispatch_chain(host, chains, sem))

    def validate(self):
        """Raises an AssertException if validation does not pass"""
        ssh.validate.validate_ssh_user(self.user)
        ssh.validate.validate_ssh_key_path(self.key_path)

        for node in self.__targets:
            ssh.validate.validate_ssh_port(node.port)
