import json
import logging
import pprint
import re

log = logging.getLogger(__name__)


def print_header(string):
    delimiter = '====>'
    log.warning('{:5s} {:6s}'.format(delimiter, string))


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

    def print_data(self):
        print_header('OUTPUT FOR {}'.format(self.stage_name))
        if len(self.failed_data) > 0:
            for host in self.failed_data:
                for ip, data in host.items():
                    log = logging.getLogger(str(ip))
                    log.error('====> {} FAILED'.format(ip))
                    log.debug('     CODE:\n{}'.format(data['returncode']))
                    log.error('     TASK:\n{}'.format(' '.join(data['cmd'])))
                    log.error('     STDERR:')
                    self.color_preflight(host=ip, rc=data['returncode'], data_array=data['stderr'])
                    log.error('     STDOUT:')
                    self.color_preflight(host=ip, rc=data['returncode'], data_array=data['stdout'])
                    log.info('')

        if len(self.success_data) > 0:
            for host in self.success_data:
                for ip, data in host.items():
                    log = logging.getLogger(str(ip))
                    log.debug('====> {} SUCCESS'.format(ip))
                    log.debug('     CODE:{}'.format(data['returncode']))
                    log.debug('     TASK:{}'.format(' '.join(data['cmd'])))
                    log.debug('     STDERR:')
                    self.color_preflight(host=ip, rc=data['returncode'], data_array=data['stderr'])
                    log.debug('     STDOUT:')
                    self.color_preflight(host=ip, rc=data['returncode'], data_array=data['stdout'])
                    log.debug('')

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

    def color_preflight(self, host='NULL', rc=0, data_array=[]):
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
