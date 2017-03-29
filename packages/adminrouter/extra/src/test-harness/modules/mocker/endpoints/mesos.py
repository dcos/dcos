# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""Mesos mock endpoint"""

import copy
import logging

from exceptions import EndpointException
from mocker.endpoints.recording import (
    RecordingHTTPRequestHandler,
    RecordingTcpIpEndpoint,
)

# pylint: disable=C0103
log = logging.getLogger(__name__)

INITIAL_STATEJSON = {
    "cluster": "prozlach-qzpz04t",
    "frameworks": [
        {
            "TASK_ERROR": 0,
            "TASK_FAILED": 0,
            "TASK_FINISHED": 0,
            "TASK_KILLED": 0,
            "TASK_KILLING": 0,
            "TASK_LOST": 0,
            "TASK_RUNNING": 0,
            "TASK_STAGING": 0,
            "TASK_STARTING": 0,
            "active": True,
            "capabilities": [],
            "hostname": "10.0.5.35",
            "id": "de1baf83-c36c-4d23-9cb0-f89f596cd6ab-0001",
            "name": "metronome",
            "offered_resources": {
                "cpus": 0.0,
                "disk": 0.0,
                "gpus": 0.0,
                "mem": 0.0
            },
            "pid": "scheduler-f43b84ec-16c3-455c-94df-158885642b88@10.0.5.35:36857",
            "slave_ids": [],
            "used_resources": {
                "cpus": 0.0,
                "disk": 0.0,
                "gpus": 0.0,
                "mem": 0.0
            },
            "webui_url": "http://10.0.5.35:9090"
        },
        {
            "TASK_ERROR": 0,
            "TASK_FAILED": 0,
            "TASK_FINISHED": 0,
            "TASK_KILLED": 0,
            "TASK_KILLING": 0,
            "TASK_LOST": 0,
            "TASK_RUNNING": 0,
            "TASK_STAGING": 0,
            "TASK_STARTING": 0,
            "active": True,
            "capabilities": [
                "TASK_KILLING_STATE",
                "PARTITION_AWARE"
            ],
            "hostname": "10.0.5.35",
            "id": "de1baf83-c36c-4d23-9cb0-f89f596cd6ab-0000",
            "name": "marathon",
            "offered_resources": {
                "cpus": 0.0,
                "disk": 0.0,
                "gpus": 0.0,
                "mem": 0.0
            },
            "pid": "scheduler-43d78acd-8c22-4a42-82e5-43c64407038c@10.0.5.35:38457",
            "slave_ids": [],
            "used_resources": {
                "cpus": 0.0,
                "disk": 0.0,
                "gpus": 0.0,
                "mem": 0.0
            },
            "webui_url": "https://10.0.5.35:8443"
        }
    ],
    "hostname": "10.0.5.35",
    "slaves": [
        {
            "TASK_ERROR": 0,
            "TASK_FAILED": 0,
            "TASK_FINISHED": 0,
            "TASK_KILLED": 0,
            "TASK_KILLING": 0,
            "TASK_LOST": 0,
            "TASK_RUNNING": 0,
            "TASK_STAGING": 0,
            "TASK_STARTING": 0,
            "active": True,
            "attributes": {},
            "framework_ids": [],
            "hostname": "127.0.0.2",
            "id": "de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1",
            "offered_resources": {
                "cpus": 0.0,
                "disk": 0.0,
                "gpus": 0.0,
                "mem": 0.0
            },
            "pid": "slave(1)@127.0.0.2:15001",
            "registered_time": 1480619701.48294,
            "reserved_resources": {},
            "resources": {
                "cpus": 4.0,
                "disk": 35577.0,
                "gpus": 0.0,
                "mem": 14018.0,
                "ports": ("[1025-2180, 2182-3887, 3889-5049,"
                          "5052-8079, 8082-8180, 8182-32000]")
            },
            "unreserved_resources": {
                "cpus": 4.0,
                "disk": 35577.0,
                "gpus": 0.0,
                "mem": 14018.0,
                "ports": ("[1025-2180, 2182-3887, 3889-5049,"
                          "5052-8079, 8082-8180, 8182-32000]")
            },
            "used_resources": {
                "cpus": 0.0,
                "disk": 0.0,
                "gpus": 0.0,
                "mem": 0.0
            },
            "version": "1.2.0"
        },
        {
            "TASK_ERROR": 0,
            "TASK_FAILED": 0,
            "TASK_FINISHED": 0,
            "TASK_KILLED": 0,
            "TASK_KILLING": 0,
            "TASK_LOST": 0,
            "TASK_RUNNING": 0,
            "TASK_STAGING": 0,
            "TASK_STARTING": 0,
            "active": True,
            "attributes": {
                "public_ip": "true"
            },
            "framework_ids": [],
            "hostname": "127.0.0.3",
            "id": "de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S0",
            "offered_resources": {
                "cpus": 0.0,
                "disk": 0.0,
                "gpus": 0.0,
                "mem": 0.0
            },
            "pid": "slave(1)@127.0.0.3:15002",
            "registered_time": 1480619699.20796,
            "reserved_resources": {
                "slave_public": {
                    "cpus": 4.0,
                    "disk": 35577.0,
                    "gpus": 0.0,
                    "mem": 14018.0,
                    "ports": "[1-21, 23-5050, 5052-32000]"
                }
            },
            "resources": {
                "cpus": 4.0,
                "disk": 35577.0,
                "gpus": 0.0,
                "mem": 14018.0,
                "ports": "[1-21, 23-5050, 5052-32000]"
            },
            "unreserved_resources": {
                "cpus": 0.0,
                "disk": 0.0,
                "gpus": 0.0,
                "mem": 0.0
            },
            "used_resources": {
                "cpus": 0.0,
                "disk": 0.0,
                "gpus": 0.0,
                "mem": 0.0
            },
            "version": "1.2.0"
        },
        {
            "TASK_ERROR": 0,
            "TASK_FAILED": 0,
            "TASK_FINISHED": 0,
            "TASK_KILLED": 0,
            "TASK_KILLING": 0,
            "TASK_LOST": 0,
            "TASK_RUNNING": 0,
            "TASK_STAGING": 0,
            "TASK_STARTING": 0,
            "active": True,
            "attributes": {
                "public_ip": "true"
            },
            "framework_ids": [],
            "hostname": "127.0.0.1",
            "id": "35f210bb-bb58-4559-9932-b62619e72b6d-S0",
            "offered_resources": {
                "cpus": 0.0,
                "disk": 0.0,
                "gpus": 0.0,
                "mem": 0.0
            },
            "pid": "slave(1)@127.0.0.1:15401",
            "registered_time": 1480619699.20796,
            "reserved_resources": {
                "slave_public": {
                    "cpus": 4.0,
                    "disk": 35577.0,
                    "gpus": 0.0,
                    "mem": 14018.0,
                    "ports": "[1-21, 23-5050, 5052-32000]"
                }
            },
            "resources": {
                "cpus": 4.0,
                "disk": 35577.0,
                "gpus": 0.0,
                "mem": 14018.0,
                "ports": "[1-21, 23-5050, 5052-32000]"
            },
            "unreserved_resources": {
                "cpus": 0.0,
                "disk": 0.0,
                "gpus": 0.0,
                "mem": 0.0
            },
            "used_resources": {
                "cpus": 0.0,
                "disk": 0.0,
                "gpus": 0.0,
                "mem": 0.0
            },
            "version": "1.2.0"
        }
    ]
}

EXTRA_SLAVE_DICT = {
    "id": "8ad5a85c-c14b-4cca-a089-b9dc006e7286-S2",
    "pid": "slave(1)@127.0.0.4:15003",
    "hostname": "127.0.0.4",
    "registered_time": 1484580645.5393,
    "resources": {
        "disk": 35577.0,
        "mem": 14018.0,
        "gpus": 0.0,
        "cpus": 4.0,
        "ports": "[1025-2180, 2182-3887, 3889-5049, 5052-8079, 8082-8180, 8182-32000]"
    },
    "used_resources": {
        "disk": 0.0,
        "mem": 0.0,
        "gpus": 0.0,
        "cpus": 0.0
    },
    "offered_resources": {
        "disk": 0.0,
        "mem": 0.0,
        "gpus": 0.0,
        "cpus": 0.0
    },
    "reserved_resources": {},
    "unreserved_resources": {
        "disk": 35577.0,
        "mem": 14018.0,
        "gpus": 0.0,
        "cpus": 4.0,
        "ports": "[1025-2180, 2182-3887, 3889-5049, 5052-8079, 8082-8180, 8182-32000]"
    },
    "attributes": {},
    "active": True,
    "version": "1.2.0",
    "TASK_STAGING": 0,
    "TASK_STARTING": 0,
    "TASK_RUNNING": 0,
    "TASK_KILLING": 0,
    "TASK_FINISHED": 0,
    "TASK_KILLED": 0,
    "TASK_FAILED": 0,
    "TASK_LOST": 0,
    "TASK_ERROR": 0,
    "framework_ids": []
}


# pylint: disable=R0903
class MesosHTTPRequestHandler(RecordingHTTPRequestHandler):
    """A request hander class mimicking Mesos master daemon.
    """
    def _calculate_response(self, base_path, *_):
        """Reply with a static Mesos state-summary response.

        Please refer to the description of the BaseHTTPRequestHandler class
        for details on the arguments and return value of this method.

        Raises:
            EndpointException: request URL path is unsupported
        """
        if base_path != '/master/state-summary':
            msg = "Path `{}` is not supported yet".format(base_path)
            blob = msg.encode('utf-8')
            raise EndpointException(code=500, reason=blob)

        ctx = self.server.context

        with ctx.lock:
            blob = self._convert_data_to_blob(ctx.data['endpoint-content'])

        return 200, 'application/json', blob


# pylint: disable=R0903,C0103
class MesosEndpoint(RecordingTcpIpEndpoint):
    """An endpoint that mimics DC/OS leader.mesos Mesos"""
    def __init__(self, port, ip=''):
        super().__init__(port, ip, MesosHTTPRequestHandler)
        self._context.data["endpoint-content"] = copy.deepcopy(INITIAL_STATEJSON)

    def reset(self, *_):
        """Reset the endpoint to the default/initial state."""
        with self._context.lock:
            super().reset()
            self._context.data["endpoint-content"] = copy.deepcopy(INITIAL_STATEJSON)

    def enable_extra_slave(self, *_):
        """Change returned JSON to include extra slave - as if cluster had three
        """
        with self._context.lock:
            self._context.data["endpoint-content"]["slaves"].append(EXTRA_SLAVE_DICT)
