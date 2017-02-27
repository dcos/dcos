# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""This module defines all the custom exceptions used in test harness"""


class ARTestHarnessException(Exception):
    """Base exception from which all test-harness exceptions must inherit"""
    pass


class EndpointException(ARTestHarnessException):
    """Signal error in processing request by endpoint

    This exception is used to signalize an error condition in processing a request
    by an endpoint. It is also used to short-circuit execution and immediately
    send an error response to the client if necessary.

    Attributes:
        code (int): HTTP code to sent to the client
        reason (b''): body of the response to send to the client
        content_type (str): content type of the body provided by 'reason' param

    """
    code = None
    reason = None
    content_type = None

    def __init__(self,
                 code='500',
                 reason=b'Error occurred, please check the logs',
                 content_type='text/plain; charset=utf-8'):
        super().__init__()
        self.code = code
        self.reason = reason
        self.content_type = content_type


class LogSourceEmpty(ARTestHarnessException):
    """Signal the end of data for log lines source.

    Exception used to signalize that the application producing the logs has
    terminated and that log gathering structures for it should be cleaned up"""
    pass
