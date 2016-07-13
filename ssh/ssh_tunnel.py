"""
Module for creating persistent SSH connections for use with synchronous
commands. Typically, tunnels should be invoked with a context manager to
ensure proper cleanup. E.G.:
with contextlib.closing(SSHTunnel(*args, **kwargs)) as tunnel:
    tunnel.write_to_remote('/usr/local/usrpath/testfile.txt', 'test_file.txt')
    tunnel.remote_cmd(['cat', 'test_file.txt'])
"""
import logging
import tempfile
from contextlib import closing
from subprocess import PIPE, Popen, TimeoutExpired, check_call, check_output

logger = logging.getLogger(__name__)


class SSHTunnel():

    def __init__(self, ssh_user, ssh_key_path, host, port=22):
        """Persistent SSH tunnel to avoid re-creating the same connection
        Note: this should always be instantiated with contextlib.closing
            e.g.: "with closing(SSHTunnel(*args, **kwargs)) as tunnel:"

        Args:
            ssh_user: (str) user with access to host
            ssh_key_path: (str) local path w/ permissions to ssh_user@host
            host: (str) locally resolvable hostname to tunnel to
            port: (int) port to connect to host via

        Return:
            established SSHTunnel that can be issued copy/cmd/close
        """
        self.socket_dir = tempfile.mkdtemp()
        self.host = host
        self.ssh_user = ssh_user
        self.ssh_key_path = ssh_key_path
        self.target = ssh_user + '@' + host
        self.port = port
        self.ssh_cmd = [
            '/usr/bin/ssh',
            '-oConnectTimeout=10',
            '-oControlMaster=auto',
            '-oControlPath={}/%C'.format(self.socket_dir),
            '-oStrictHostKeyChecking=no',
            '-oUserKnownHostsFile=/dev/null',
            '-oBatchMode=yes',
            '-oPasswordAuthentication=no']

        start_tunnel = self.ssh_cmd + [
            '-fnN',
            '-i',  ssh_key_path,
            '-p', str(port), self.target]
        logger.debug('Starting SSH tunnel: ' + ' '.join(start_tunnel))
        check_call(start_tunnel)
        logger.debug('SSH Tunnel established!')

    def remote_cmd(self, cmd, timeout=None, return_process=False):
        """
        Args:
            cmd: list of strings that will be interpretted in a subprocess
            timeout: (int) number of seconds until process timesout
            return_process: (bool) instead of returning output from cmd,
                return the Popen handler. Consumer must implement timeout
        """
        assert isinstance(cmd, list), 'cmd must be a list'
        if timeout:
            assert isinstance(timeout, int), 'timeout must be an int (seconds)'
        run_cmd = self.ssh_cmd + ['-p', str(self.port), self.target] + cmd
        logger.debug('Running socket cmd: ' + ' '.join(run_cmd))
        try:
            if return_process:
                return Popen(run_cmd, stdout=PIPE)
            else:
                return check_output(run_cmd, timeout=timeout)
        except TimeoutExpired as e:
            logging.exception('{} timed out after {} seconds'.format(cmd, timeout))
            logging.debug('Timed out process output:\n' + e.output)
            raise

    def write_to_remote(self, src, dst):
        """
        Args:
            src: (str) local path representing source data
            dst: (str) destination for path
        """
        cmd = self.ssh_cmd + ['-C', '-p', str(self.port), self.target, 'cat>'+dst]
        logger.debug('Running socket write: ' + ' '.join(cmd))
        with open(src, 'r') as fh:
            check_call(cmd, stdin=fh)

    def close(self):
        close_tunnel = self.ssh_cmd + ['-p', str(self.port), '-O', 'exit', self.target]
        logger.debug('Closing SSH Tunnel: ' + ' '.join(close_tunnel))
        check_call(close_tunnel)
        check_call(['rm', '-rf', self.socket_dir])


class TunnelCollection():

    def __init__(self, ssh_user, ssh_key_path, host_names):
        """Convenience collection of SSHTunnels so that users can keep
        multiple connections alive with a single self-closing context
        Args:
            ssh_user: (str) user with access to host
            ssh_key_path: (str) local path w/ permissions to ssh_user@host
            host_names: list of locally resolvable hostname:port to tunnel to
        """
        assert isinstance(host_names, list)
        logger.debug('Creating TunnelCollection for the following: ' + str(host_names))
        self.tunnels = []
        for host in host_names:
            hostname, port = host.split(':')
            self.tunnels.append(SSHTunnel(ssh_user, ssh_key_path, hostname, port=port))
        logger.debug('Successfully created TunnelCollection')

    def close(self):
        for tunnel in self.tunnels:
            tunnel.close()


def run_ssh_cmd(ssh_user, ssh_key_path, host, cmd, port=22):
    """Convenience function to do a one-off SSH command
    """
    assert isinstance(cmd, list)
    with closing(SSHTunnel(ssh_user, ssh_key_path, host, port=port)) as tunnel:
        return tunnel.remote_cmd(cmd)


def run_scp_cmd(ssh_user, ssh_key_path, host, src, dst, port=22):
    """Convenience function to do a one-off SSH copy
    """
    with closing(SSHTunnel(ssh_user, ssh_key_path, host, port=port)) as tunnel:
        tunnel.write_to_remote(src, dst)
