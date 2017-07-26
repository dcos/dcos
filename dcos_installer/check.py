from collections import namedtuple


Check = namedtuple('Check', ['name', 'status', 'status_text', 'output'])


class CheckRunnerResult:

    statuses = {
        0: 'OK',
        1: 'WARNING',
        2: 'CRITICAL',
        3: 'UNKNOWN'}

    def __init__(self, check_runner_response: dict):
        self.validate_response(check_runner_response)
        self.response = check_runner_response

    @property
    def is_error(self):
        return self.is_error_response(self.response)

    @property
    def error_message(self):
        if not self.is_error:
            raise Exception('error_message only available if is_error is True')
        return self.response['error']

    @property
    def status(self):
        if self.is_error:
            raise Exception('status only available if is_error is False')
        return self.response['status']

    @property
    def status_text(self):
        if self.is_error:
            raise Exception('status_text only available if is_error is False')
        return self.statuses[self.status]

    @property
    def checks(self):
        if self.is_error:
            raise Exception('checks only available if is_error is False')
        return {
            name: Check(
                name=name,
                status=result['status'],
                status_text=self.statuses[result['status']],
                output=result['output'])
            for name, result in self.response['checks'].items()
        }

    @classmethod
    def validate_response(cls, response: dict):
        if cls.is_error_response(response):
            cls._validate_check_runner_error_response(response)
        else:
            cls._validate_check_runner_success_response(response)

    @staticmethod
    def is_error_response(response: dict):
        return 'error' in response.keys()

    @staticmethod
    def _validate_check_error_response(response):
        if 'error' not in response.keys():
            raise Exception('Check runner error response is missing expected key \'error\'')

        for key in ['status', 'checks']:
            if key in response.keys():
                raise Exception('Check runner error response has unexpected key \'{}\' '.format(key))

    @classmethod
    def _validate_check_runner_success_response(cls, response: dict):
        if 'error' in response.keys():
            raise Exception('Check runner response has unexpected key \'error\'')

        for key in ['status', 'checks']:
            if key not in response.keys():
                raise Exception('Check runner response is missing expected key \'{}\''.format(key))

        if response['status'] not in cls.statuses.keys():
            raise Exception('Unexpected aggregate check status: {}'.format(response['status']))

        for check_name, check_result in response['checks'].items():
            if 'status' not in check_result.keys():
                raise Exception('Result for check {} is missing expected key \'status\''.format(check_name))

            if check_result['status'] not in cls.statuses.keys():
                raise Exception('Unexpected status for check {}: {}'.format(check_name, check_result['status']))
