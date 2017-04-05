# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""
Management code for DC/OS mocks used by Open AR instances.
"""

import logging

from mocker.common import MockerBase
from mocker.endpoints.open.iam import IamEndpoint
from mocker.endpoints.reflectors import (
    ReflectingTcpIpEndpoint,
)

log = logging.getLogger(__name__)


class Mocker(MockerBase):
    """This class represents mocking behaviour specific to Open variant of the
    repo."""
    def __init__(self):
        """Initialize new Mocker instance"""
        extra_endpoints = []

        # DDDT:
        extra_endpoints.append(
            ReflectingTcpIpEndpoint(ip='127.0.0.1', port=1050))
        # Open DC/OS IAM
        extra_endpoints.append(IamEndpoint(ip='127.0.0.1', port=8101))

        super().__init__(extra_endpoints)
