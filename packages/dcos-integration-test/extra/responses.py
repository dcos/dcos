"""Module that holds expected repsonses."""
import requests


class Ok():

    def __init__(self, expected_body=None):
        self.expected_body = expected_body
        self.expected_code = 200

    def __eq__(self, other):
        if isinstance(other, requests.Response):
            return self._is_equal_to(other)
        else:
            return False

    def _is_equal_to(self, response):
        code = response.status_code == self.expected_code
        body = self.expected_body == response.text if self.expected_body is not None else True
        return code and body
