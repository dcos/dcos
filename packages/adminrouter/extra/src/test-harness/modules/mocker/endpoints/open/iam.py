# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""IAM mock endpoint.
"""

import logging

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

    Attributes:
        USERS_PATH_PREFIX (str): API path under which users endpoint should
            be available. The uid of the user is extracted from request path
            itself.
    """
    USERS_PATH_PREFIX = '/acs/api/v1/users/'

    def _calculate_response(self, base_path, *_):
        """Answer the query for user data basing on the endpoint context.

        Please refer to the description of the BaseHTTPRequestHandler class
        for details on the arguments and return value of this method.

        Raises:
            EndpointException: request URL path is unsupported
        """
        ctx = self.server.context

        with ctx.lock:
            # copy.deepcopy() can also be used here, instead of locking
            users = ctx.data['users']

            if not base_path.startswith(self.USERS_PATH_PREFIX) or \
                    base_path == self.USERS_PATH_PREFIX:
                msg = "Path `{}` is not supported yet".format(base_path)
                blob = msg.encode('utf-8')
                raise EndpointException(code=500, reason=blob)

            uid = base_path[len(self.USERS_PATH_PREFIX):]

            if uid not in users:
                res = {"title": "Bad Request",
                       "description": "User `{}` not known.".format(uid),
                       "code": "ERR_UNKNOWN_USER_ID"
                       }

                blob = self._convert_data_to_blob(res)
                raise EndpointException(code=400,
                                        reason=blob,
                                        content_type='application/json')

            return self._convert_data_to_blob(users[uid])


class IamEndpoint(RecordingTcpIpEndpoint):
    """Endpoint that mimics DC/OS IAM.

    Attributes:
        users: list of users defined in the mock by default.
    """
    users = ["root", "bozydar", "jadwiga"]

    @staticmethod
    def _user_dict_from_uid(uid):
        """Helper function that creates default user data basing on the provided
           uid.
        """
        return {"is_remote": False,
                "uid": uid,
                "url": "/acs/api/v1/users/{}".format(uid),
                "description": "user `{}`".format(uid),
                "is_service": False
                }

    def reset(self, *_):
        """Reset the endpoint to the default/initial state."""
        with self._context.lock:
            super().reset()
            self._context.data["users"] = {
                uid: self._user_dict_from_uid(uid) for uid in self.users}

    # pylint: disable=C0103
    def __init__(self, port, ip=''):
        """Initialize a new IamEndpoint"""
        super().__init__(port, ip, IamHTTPRequestHandler)
        self._context.data["users"] = {
            uid: self._user_dict_from_uid(uid) for uid in self.users}

    def add_user(self, aux):
        """Add UID/user to the endpoint, so that it starts responding with
        200 OK to queries about it.
        """
        uid = aux["uid"]
        with self._context.lock:
            users = self._context.data["users"]

            assert uid not in users, "User already defined"

            users[uid] = self._user_dict_from_uid(uid)

        log.debug("User `%s` has been added to IamEndpoint", uid)

    def del_user(self, aux):
        """Remove UID/user from the endpoint. Queries for it will no longer
        result in 200 OK
        """
        uid = aux["uid"]
        with self._context.lock:
            users = self._context.data["users"]

            assert uid in users, "User does not exist yet"

            del users[uid]

        log.debug("User `%s` has been removed from IamEndpoint", uid)
