# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import logging
import re

from exceptions import EndpointException
from mocker.endpoints.recording import (
    RecordingHTTPRequestHandler,
    RecordingTcpIpEndpoint,
)

# pylint: disable=C0103
log = logging.getLogger(__name__)


# pylint: disable=R0903
class IamHTTPRequestHandler(RecordingHTTPRequestHandler):
    """A request hander class mimicking DC/OS IAM operation.
    """

    USERS_QUERY_REGEXP = re.compile('^/acs/api/v1/users/([^/]+)$')

    def _calculate_response(self, base_path, url_args, body_args=None):
        """Reply with the currently set mock-reply for given IAM user query.

        Please refer to the description of the BaseHTTPRequestHandler class
        for details on the arguments and return value of this method.

        Raises:
            EndpointException: request URL path is unsupported
        """
        match = self.USERS_QUERY_REGEXP.search(base_path)
        if match:
            return self.__users_permissions_request_handler(match.group(1))

        if base_path == '/acs/api/v1/reflect/me':
            # A test URI that is used by tests. In some cases it is impossible
            # to reuse /acs/api/v1/users/ path.
            return self._reflect_request(base_path, url_args, body_args)

        raise EndpointException(
            code=500,
            content="Path `{}` is not supported yet".format(base_path))

    def __users_permissions_request_handler(self, uid):
        ctx = self.server.context

        if not ctx.data['allowed']:
            res = {
                "title": "Bad Request",
                "description": "User `{}` not known.".format(uid),
                "code": "ERR_UNKNOWN_USER_ID"}

            blob = self._convert_data_to_blob(res)
            return 404, 'application/json', blob

        blob = self._convert_data_to_blob({
            "uid": uid,
            "user_data": True
        })
        return 200, 'application/json', blob


class IamEndpoint(RecordingTcpIpEndpoint):

    def __init__(self, port, ip=''):
        """Initialize a new IamEndpoint"""
        super().__init__(port, ip, IamHTTPRequestHandler)
        self.__context_init()

    def reset(self):
        with self._context.lock:
            super().reset()
            self.__context_init()

    def __context_init(self):
        """Helper function meant to initialize all the data relevant to this
           particular type of endpoint"""
        self._context.data["allowed"] = True

    def permit_all_queries(self, *_):
        self._context.data["allowed"] = True

    def deny_all_queries(self, *_):
        self._context.data["allowed"] = False
