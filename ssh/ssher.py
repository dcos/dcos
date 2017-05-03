""" Simple, robust SSH client for basic I/O
"""
import logging
import os
import stat
import tempfile
from contextlib import contextmanager
from subprocess import check_call, check_output

from pkgpanda.util import write_string

log = logging.getLogger(__name__)


class Tunnelled():
    def __init__(self, base_cmd: list, target: str):
        """
        Args:
            base_cmd: list of strings that will be evaluated by check_call
                to send commands through the tunnel
            target: string in the form user@host
        """
        self.base_cmd = base_cmd
        self.target = target

    def command(self, cmd: list, **kwargs) -> bytes:
        """ Run a command at the tunnel target
        Args:
            cmd: list of strings that will be sent as a command to the target
            **kwargs: any keywork args that can be passed into
                subprocess.check_output. For more information, see:
                https://docs.python.org/3/library/subprocess.html#subprocess.check_output
        """
        run_cmd = self.base_cmd + [self.target] + cmd
        log.debug('Running socket cmd: ' + ' '.join(run_cmd))
        if 'stdout' in kwargs:
            return check_call(run_cmd, **kwargs)
        else:
            return check_output(run_cmd, **kwargs)

    def copy_file(self, src: str, dst: str) -> None:
        """ Copy a file from localhost to target

        Args:
            src: local path representing source data
            dst: destination for path
        """
        cmd = self.base_cmd + ['-C', self.target, 'cat>' + dst]
        log.debug('Copying {} to {}:{}'.format(src, self.target, dst))
        with open(src, 'r') as fh:
            check_call(cmd, stdin=fh)


@contextmanager
def temp_data(key: str) -> (str, str):
    """ Provides file paths for data required to establish the SSH tunnel
    Args:
        key: string containing the private SSH key

    Returns:
        (path_for_temp_socket_file, path_for_temp_ssh_key)
    """
    temp_dir = tempfile.mkdtemp()
    socket_path = temp_dir + '/control_socket'
    key_path = temp_dir + '/key'
    write_string(key_path, key)
    os.chmod(key_path, stat.S_IREAD | stat.S_IWRITE)
    yield (socket_path, key_path)
    os.remove(key_path)
    # might have been deleted already if SSH exited correctly
    if os.path.exists(socket_path):
        os.remove(socket_path)
    os.rmdir(temp_dir)


@contextmanager
def open_tunnel(user: str, key: str, host: str, port: int=22) -> Tunnelled:
    """ Provides clean setup/tear down for an SSH tunnel
    Args:
        user: SSH user
        key: string containing SSH private key
        host: string containing target host
        port: target's SSH port
    """
    target = user + '@' + host
    with temp_data(key) as temp_paths:
        base_cmd = [
            '/usr/bin/ssh',
            '-oConnectTimeout=10',
            '-oControlMaster=auto',
            '-oControlPath=' + temp_paths[0],
            '-oStrictHostKeyChecking=no',
            '-oUserKnownHostsFile=/dev/null',
            '-oBatchMode=yes',
            '-oPasswordAuthentication=no',
            '-p', str(port)]

        start_tunnel = base_cmd + ['-fnN', '-i', temp_paths[1], target]
        log.debug('Starting SSH tunnel: ' + ' '.join(start_tunnel))
        check_call(start_tunnel)
        log.debug('SSH Tunnel established!')

        yield Tunnelled(base_cmd, target)

        close_tunnel = base_cmd + ['-O', 'exit', target]
        log.debug('Closing SSH Tunnel: ' + ' '.join(close_tunnel))
        check_call(close_tunnel)


class Ssher:
    """ class for binding SSH user and key to tunnel
    """
    def __init__(self, user: str, key: str):
        self.user = user
        self.key = key

    def command(self, host: str, cmd: list, port: int=22, **kwargs) -> bytes:
        with open_tunnel(self.user, self.key, host, port) as tunnel:
            return tunnel.command(cmd, **kwargs)

    def get_home_dir(self, host: str, port: int=22) -> str:
        """ Returns the SSH home dir
        """
        return self.command(host, ['pwd'], port=port).decode().strip()
