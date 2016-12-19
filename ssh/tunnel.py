"""
Module for creating persistent SSH connections for use with synchronous
commands. Typically, tunnels should be invoked as a context manager to
ensure proper cleanup. E.G.:
with tunnel(*args, **kwargs) as my_tunnel:
    my_tunnel.write_to_remote('/usr/local/usrpath/testfile.txt', 'test_file.txt')
    my_tunnel.remote_cmd(['cat', 'test_file.txt'])
"""
import logging
import tempfile
from contextlib import contextmanager, ExitStack
from subprocess import check_call, check_output, TimeoutExpired
from typing import Optional

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
def tunnel(user: str, key_path: str, host: str, port: int=22):
    # This will be cleaned up by SSH when the tunnel is closed
    tunnel_socket = tempfile.NamedTemporaryFile(delete=False)
    target = user + '@' + host

    base_cmd = [
        '/usr/bin/ssh',
        '-oConnectTimeout=10',
        '-oControlMaster=auto',
        '-oControlPath=' + tunnel_socket.name,
        '-oStrictHostKeyChecking=no',
        '-oUserKnownHostsFile=/dev/null',
        '-oBatchMode=yes',
        '-oPasswordAuthentication=no',
        '-p', str(port)]

    start_tunnel = base_cmd + ['-fnN', '-i', key_path, target]
    logger.debug('Starting SSH tunnel: ' + ' '.join(start_tunnel))
    check_call(start_tunnel)
    logger.debug('SSH Tunnel established!')

    yield Tunnelled(base_cmd, host, target)

    close_tunnel = base_cmd + ['-O', 'exit', target]
    logger.debug('Closing SSH Tunnel: ' + ' '.join(close_tunnel))
    check_call(close_tunnel)


@contextmanager
def tunnel_collection(user, key_path, host_names: list):
    """Convenience collection of Tunnels so that users can keep
    multiple connections alive with a single self-closing context
    Args:
        user: user with access to host
        key_path: local path w/ permissions to user@host
        host_names: list of locally resolvable hostname:port to tunnel to
    """

    with ExitStack() as exit_stack:
        logger.debug('Creating TunnelCollection for the following: ' + str(host_names))
        tunnels = list()
        for host in host_names:
            ip, port = host.split(':')
            tunnels.append(exit_stack.enter_context(tunnel(user, key_path, ip, port)))
        logger.debug('Successfully created TunnelCollection')
        yield tunnels


def run_ssh_cmd(user, key_path, host, cmd, port=22, timeout=None):
    """Convenience function to do a one-off SSH command
    """
    with tunnel(user, key_path, host, port=port) as t:
        return t.remote_cmd(cmd, timeout=timeout)


def run_scp_cmd(user, key_path, host, src, dst, port=22):
    """Convenience function to do a one-off SSH copy
    """
    with tunnel(user, key_path, host, port=port) as t:
        t.write_to_remote(src, dst)
