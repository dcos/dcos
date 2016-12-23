"""
Module for creating persistent SSH connections for use with synchronous
commands. Typically, tunnels should be invoked as a context manager to
ensure proper cleanup. E.G.:
with tunnel(*args, **kwargs) as my_tunnel:
    my_tunnel.write_to_remote('/usr/local/usrpath/testfile.txt', 'test_file.txt')
    my_tunnel.remote_cmd(['cat', 'test_file.txt'])
"""
import logging
import os
import stat
import tempfile
from contextlib import contextmanager, ExitStack
from subprocess import check_call, check_output, TimeoutExpired
from typing import Optional

from pkgpanda.util import write_string

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Tunnelled():
    def __init__(self, base_cmd: list, host: str, target: str):
        self.base_cmd = base_cmd
        self.host = host
        self.target = target

    def remote_cmd(self, cmd: list, timeout: Optional[int]=None, stdout=None):
        """
        Args:
            cmd: list of strings that will be interpretted in a subprocess
            timeout: (int) number of seconds until process timesout
            stdout: file object to redirect stdout to
        """
        run_cmd = self.base_cmd + [self.target] + cmd
        logger.debug('Running socket cmd: ' + ' '.join(run_cmd))
        try:
            if stdout:
                return check_call(run_cmd, stdout=stdout, timeout=timeout)
            else:
                return check_output(run_cmd, timeout=timeout)
        except TimeoutExpired as e:
            logging.exception('{} timed out after {} seconds'.format(cmd, timeout))
            logging.debug('Timed out process output:\n' + e.output.decode())
            raise

    def write_to_remote(self, src: str, dst: str):
        """
        Args:
            src: local path representing source data
            dst: destination for path
        """
        cmd = self.base_cmd + ['-C', self.target, 'cat>' + dst]
        logger.debug('Running socket write: ' + ' '.join(cmd))
        with open(src, 'r') as fh:
            check_call(cmd, stdin=fh)


@contextmanager
def temp_data(key):
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
def tunnel(user: str, key: str, host: str, port: int=22):
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
        logger.debug('Starting SSH tunnel: ' + ' '.join(start_tunnel))
    # Test Code
        check_call(start_tunnel)
        logger.debug('SSH Tunnel established!')

        yield Tunnelled(base_cmd, host, target)

        close_tunnel = base_cmd + ['-O', 'exit', target]
        logger.debug('Closing SSH Tunnel: ' + ' '.join(close_tunnel))
        check_call(close_tunnel)


@contextmanager
def tunnel_collection(user, key, host_names: list):
    """Convenience collection of Tunnels so that users can keep
    multiple connections alive with a single self-closing context
    Args:
        user: user with access to host
        key: contents of private key
        host_names: list of locally resolvable hostname:port to tunnel to
    """

    with ExitStack() as exit_stack:
        logger.debug('Creating TunnelCollection for the following: ' + str(host_names))
        tunnels = list()
        for host in host_names:
            ip, port = host.split(':')
            tunnels.append(exit_stack.enter_context(tunnel(user, key, ip, port)))
        logger.debug('Successfully created TunnelCollection')
        yield tunnels
