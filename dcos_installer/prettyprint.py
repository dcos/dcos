import json
import logging
import pprint
import re
from typing import List

from dcos_installer.check import CheckRunnerResult
from dcos_installer.constants import CHECK_RUNNER_CMD


log = logging.getLogger(__name__)


def print_header(string):
    delimiter = '====>'
    log.warning('{:5s} {:6s}'.format(delimiter, string))


def is_check_command(cmd: List[str]):
    return CHECK_RUNNER_CMD in ' '.join(cmd)


class PrettyPrint():
    """
    Pretty prints the output from the deployment process.

    """
    def __init__(self, output):
        self.output = output
        self.fail_hosts = []
        self.success_hosts = []
        self.preflight = False

    def beautify(self, mode='print_data_basic'):
        self.failed_data, self.success_data = self.find_data(self.output)
        getattr(self, mode)()
        return self.failed_data, self.success_data

    def find_data(self, data):
        failed_data = []
        success_data = []
        for hosts in data:
            for host in hosts:
                for ip, results in host.items():
                    if results['returncode'] == 0:
                        if ip not in self.success_hosts:
                            self.success_hosts.append(ip)
                        success_data.append(host)

                    else:
                        if ip not in self.fail_hosts:
                            self.fail_hosts.append(ip)
                        failed_data.append(host)

        # Remove failed from success hosts
        self.success_hosts = [ip for ip in self.success_hosts if ip not in self.fail_hosts]
        return failed_data, success_data

    def _print_host_set(self, status, hosts):
        if len(hosts) > 0:
            for host in hosts:
                for ip, data in host.items():
                    log = logging.getLogger(str(ip))
                    if is_check_command(data['cmd']):
                        log.error('====> {} CHECK {}'.format(ip, status))
                        self._print_check_result(ip, data)
                    else:
                        log.error('====> {} COMMAND {}'.format(ip, status))
                        self._print_command_result(ip, data)

    @classmethod
    def _print_command_result(cls, ip, data):
        log = logging.getLogger(str(ip))
        log.debug('     CODE:\n{}'.format(data['returncode']))
        log.error('     TASK:\n{}'.format(' '.join(data['cmd'])))
        log.error('     STDERR:')
        cls.color_preflight(host=ip, rc=data['returncode'], data_array=data['stderr'])
        log.error('     STDOUT:')
        cls.color_preflight(host=ip, rc=data['returncode'], data_array=data['stdout'])
        log.info('')

    @classmethod
    def _print_check_result(cls, ip, data):
        log = logging.getLogger(str(ip))

        check_runner_response_body = '\n'.join(data['stdout'])
        try:
            check_runner_result = CheckRunnerResult(json.loads(check_runner_response_body))
        except Exception as exc:
            log.error('Failed to parse check runner response: {}'.format(exc))
            log.error(check_runner_response_body)
            raise

        if check_runner_result.is_error:
            log.error('     ERROR: ' + check_runner_result.error_message)
        else:
            log.error('     Overall status: {}'.format(check_runner_result.status_text))
            for check_name, check_result in sorted(check_runner_result.checks.items()):
                log.error('     {}: {}'.format(check_name, check_result.status_text))

                log_func = log.error
                if check_result.status == 0:
                    log_func = log.debug
                for line in check_result.output.split('\n'):
                    log_func('          {}'.format(line))

                log.info('')

    def print_data(self):
        print_header('OUTPUT FOR {}'.format(self.stage_name))
        self._print_host_set("FAILED", self.failed_data)
        self._print_host_set("PASSED", self.success_data)

    def print_summary(self):
        print_header('SUMMARY FOR {}'.format(self.stage_name))
        total = len(self.fail_hosts) + len(self.success_hosts)
        err_msg = '{} out of {} hosts successfully completed {} stage.'
        log.warning(err_msg.format(len(self.success_hosts), total, self.stage_name))
        if len(self.fail_hosts) > 0:
            log.error('The following hosts had failures detected during {} stage:'.format(self.stage_name))
            for host in self.fail_hosts:
                log.error('     {} failures detected.'.format(host))
        print_header('END OF SUMMARY FOR {}'.format(self.stage_name))

    @staticmethod
    def color_preflight(host='NULL', rc=0, data_array=[]):
        """
        A subroutine to parse the output from the dcos_install.sh script's pass or fail
        output.
        """
        log = logging.getLogger(host)
        does_pass = re.compile('PASS')
        does_fail = re.compile('FAIL')
        for line in data_array:
            if line is not None and line != '':
                if does_pass.search(line):
                    log.debug('          {}'.format(line))

                elif does_fail.search(line):
                    log.error('          {}'.format(line))

                elif rc != 0:
                    log.error('          {}'.format(line))

                else:
                    log.debug('          {}'.format(line))

    def print_json(self):
        pprint.pprint(json.dumps(self.output))
