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

FRAMEWORK_TEMPLATE = {
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
    "id": "09058589-9e78-4da8-8aa5-a97aee7a8bea-0000",
    "name": "scheduler-alwaysthere",
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
    "webui_url": "https://127.0.0.1:16000"
}


def framework_from_template(fid, name, webui_url):
    """Create a Mesos framework entry basing on the supplied data and the template

    Arguments:
        sid (string): framework ID that the new framework should have
        port (string): TCP/IP port that the new framework should pretend to
            listen on
        ip (string): IP address that the new framework hould pretend to listen on

    Returns:
        Framework dict mimicing the one returned by Marathon
    """
    res = copy.deepcopy(FRAMEWORK_TEMPLATE)
    res['id'] = fid
    res['name'] = name
    res['webui_url'] = webui_url

    return res

SCHEDULER_FWRK_MARATHON_ID = '819aed93-4143-4291-8ced-5afb5c726803-0000'  # noqa: E305
SCHEDULER_FWRK_ALWAYSTHERE_ID = '0f8899bf-a31a-44d5-b1a5-c8c3f7128905-0000'  # noqa: E305
SCHEDULER_FWRK_ALWAYSTHERE_NEST1_ID = '4bfed1de-5c6c-48fa-931c-9f0468387db5-0000'  # noqa: E305
SCHEDULER_FWRK_ALWAYSTHERE_NEST2_ID = '08cc2799-9380-469f-82ca-e4527ced3d8b-0000'  # noqa: E305
SCHEDULER_FWRK_ONLYMESOS_NEST2_ID = '2795e97a-19c6-48a7-b55c-fb806bba8f02-0000'  # noqa: E305
SCHEDULER_FWRK_ONLYMESOSDNS_NEST2_ID = \
    '7b602083-218a-4f88-8741-81557f1c381a-0000'  # noqa: E305

SCHEDULER_FWRK_MARATHON = framework_from_template(
    SCHEDULER_FWRK_MARATHON_ID,
    "marathon",
    "http://127.0.0.1:8080")
SCHEDULER_FWRK_ALWAYSTHERE = framework_from_template(
    SCHEDULER_FWRK_ALWAYSTHERE_ID,
    "scheduler-alwaysthere",
    "http://127.0.0.1:16000")
SCHEDULER_FWRK_ALWAYSTHERE_DIFFERENTPORT = framework_from_template(
    SCHEDULER_FWRK_ALWAYSTHERE_ID,
    "scheduler-alwaysthere",
    "http://127.0.0.15:16001")
SCHEDULER_FWRK_ALWAYSTHERE_NOWEBUI = framework_from_template(
    SCHEDULER_FWRK_ALWAYSTHERE_ID,
    "scheduler-alwaysthere",
    "")
SCHEDULER_FWRK_ALWAYSTHERE_NEST1 = framework_from_template(
    SCHEDULER_FWRK_ALWAYSTHERE_NEST1_ID,
    'nest1/scheduler-alwaysthere',
    "http://127.0.0.1:17000")
SCHEDULER_FWRK_ALWAYSTHERE_NEST2 = framework_from_template(
    SCHEDULER_FWRK_ALWAYSTHERE_NEST2_ID,
    'nest2/nest1/scheduler-alwaysthere',
    "http://127.0.0.1:18000")
SCHEDULER_FWRK_ONLYMESOS_NEST2 = framework_from_template(
    SCHEDULER_FWRK_ONLYMESOS_NEST2_ID,
    'nest2/nest1/scheduler-onlymesos',
    "http://127.0.0.1:18002")
SCHEDULER_FWRK_ONLYMESOSDNS_NEST2 = framework_from_template(
    SCHEDULER_FWRK_ONLYMESOSDNS_NEST2_ID,
    'nest2/nest1/scheduler-onlymesosdns',
    "")

AGENT_TEMPLATE = {
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


def agent_from_template(sid, ip, port):
    """Create a Mesos agent entry basing on the supplied data and the template

    Arguments:
        sid (string): agent ID that the new agent should have
        port (string): TCP/IP port that the new agent should pretend to listen on
        ip (string): IP address that the new agent hould pretend to listen on

    Returns:
        Slave dict mimicing the one returned by Marathon
    """
    res = copy.deepcopy(AGENT_TEMPLATE)
    res['id'] = sid
    res['pid'] = "slave(1)@{0}:{1}".format(ip, port)
    res['hostname'] = ip

    return res

AGENT1_ID = "de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1"  # noqa: E305
AGENT2_ID = "de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S0"  # noqa: E305
AGENT3_ID = "35f210bb-bb58-4559-9932-b62619e72b6d-S0"  # noqa: E305
AGENT_EXTRA_ID = "8ad5a85c-c14b-4cca-a089-b9dc006e7286-S2"  # noqa: E305

AGENT1_DICT = agent_from_template(
    AGENT1_ID,
    "127.0.0.2",
    "15001",
    )
AGENT2_DICT = agent_from_template(
    AGENT2_ID,
    "127.0.0.3",
    "15002",
    )
AGENT3_DICT = agent_from_template(
    AGENT3_ID,
    "127.0.0.1",
    "15401",
    )
EXTRA_AGENT_DICT = agent_from_template(
    AGENT_EXTRA_ID,
    "127.0.0.4",
    "15003",
    )

INITIAL_STATEJSON = {
    "cluster": "prozlach-qzpz04t",
    "frameworks": [SCHEDULER_FWRK_MARATHON,
                   SCHEDULER_FWRK_ALWAYSTHERE,
                   SCHEDULER_FWRK_ALWAYSTHERE_NEST1,
                   SCHEDULER_FWRK_ALWAYSTHERE_NEST2,
                   SCHEDULER_FWRK_ONLYMESOS_NEST2,
                   SCHEDULER_FWRK_ONLYMESOSDNS_NEST2,
                   ],
    "hostname": "10.0.5.35",
    "slaves": [AGENT1_DICT,
               AGENT2_DICT,
               AGENT3_DICT,
               ],
}


# pylint: disable=R0903
class MesosHTTPRequestHandler(RecordingHTTPRequestHandler):
    """A request hander class mimicking Mesos master daemon.
    """
    def _calculate_response(self, base_path, url_args, body_args=None):
        """Reply with a static Mesos state-summary response.

        Please refer to the description of the BaseHTTPRequestHandler class
        for details on the arguments and return value of this method.

        Raises:
            EndpointException: request URL path is unsupported
        """
        if base_path == '/reflect/me':
            # A test URI that is used by tests. In some cases it is impossible
            # to reuse /master/state-summary path.
            return self._reflect_request(base_path, url_args, body_args)

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
        self.__context_init()

    def reset(self, *_):
        """Reset the endpoint to the default/initial state."""
        with self._context.lock:
            super().reset()
            self.__context_init()

    def __context_init(self):
        """Helper function meant to initialize all the data relevant to this
           particular type of endpoint"""
        self._context.data["endpoint-content"] = copy.deepcopy(INITIAL_STATEJSON)

    def enable_extra_agent(self, *_):
        """Change returned JSON to include extra agent, one that is by default
           not present in mocked `/state-json summary`
        """
        with self._context.lock:
            self._context.data["endpoint-content"]["slaves"].append(EXTRA_AGENT_DICT)

    def set_frameworks_response(self, frameworks):
        """Set response content for frameworks section of /state-summary response

        Arguments:
            frameworks (list): a list of framework dicts describing mocked
                frameworks.
        """
        with self._context.lock:
            self._context.data["endpoint-content"]["frameworks"] = frameworks
