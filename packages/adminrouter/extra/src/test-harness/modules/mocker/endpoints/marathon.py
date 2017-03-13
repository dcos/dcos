# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""Marathon mock endpoint"""

import logging

from exceptions import EndpointException
from mocker.endpoints.recording import (
    RecordingHTTPRequestHandler,
    RecordingTcpIpEndpoint,
)

# pylint: disable=C0103
log = logging.getLogger(__name__)

NGINX_APP_ALWAYSTHERE = {
    "id": "/nginx-alwaysthere",
    "cmd": ("cd /opt/bitnami/nginx && harpoon initialize nginx && "
            "rm -rf /opt/bitnami/nginx/html && ln -s "
            "/mnt/mesos/sandbox/hello-nginx-master/ /opt/bitnami/nginx/html "
            "&& harpoon start --foreground nginx"),
    "args": None,
    "user": None,
    "env": {},
    "instances": 1,
    "cpus": 1,
    "mem": 1024,
    "disk": 0,
    "gpus": 0,
    "executor": "",
    "constraints": [],
    "uris": [
        "https://github.com/mesosphere/hello-nginx/archive/master.zip"
    ],
    "fetch": [
        {
            "uri": "https://github.com/mesosphere/hello-nginx/archive/master.zip",
            "extract": True,
            "executable": False,
            "cache": False
        }
    ],
    "storeUrls": [],
    "backoffSeconds": 1,
    "backoffFactor": 1.15,
    "maxLaunchDelaySeconds": 3600,
    "container": {
        "type": "DOCKER",
        "volumes": [],
        "docker": {
            "image": "bitnami/nginx:1.10.2-r0",
            "network": "BRIDGE",
            "portMappings": [
                {
                    "containerPort": 80,
                    "hostPort": 0,
                    "servicePort": 10000,
                    "protocol": "tcp",
                    "labels": {}
                },
                {
                    "containerPort": 443,
                    "hostPort": 0,
                    "servicePort": 10001,
                    "protocol": "tcp",
                    "labels": {}
                }
            ],
            "privileged": False,
            "parameters": [],
            "forcePullImage": False
        }
    },
    "healthChecks": [
        {
            "gracePeriodSeconds": 300,
            "intervalSeconds": 60,
            "timeoutSeconds": 20,
            "maxConsecutiveFailures": 3,
            "delaySeconds": 15,
            "command": {
                "value": "harpoon status nginx | grep -q 'com.bitnami.nginx is running'"
            },
            "protocol": "COMMAND"
        }
    ],
    "readinessChecks": [],
    "dependencies": [],
    "upgradeStrategy": {
        "minimumHealthCapacity": 1,
        "maximumOverCapacity": 1
    },
    "labels": {
        "DCOS_PACKAGE_RELEASE": "5",
        "DCOS_SERVICE_SCHEME": "http",
        "DCOS_PACKAGE_SOURCE": "https://universe.mesosphere.com/repo",
        "DCOS_PACKAGE_METADATA": "blah, blah, bleh",
        "DCOS_PACKAGE_REGISTRY_VERSION": "2.0",
        "DCOS_SERVICE_NAME": "nginx-alwaysthere",
        "DCOS_SERVICE_PORT_INDEX": "0",
        "DCOS_PACKAGE_VERSION": "1.10.2",
        "DCOS_PACKAGE_NAME": "nginx",
        "DCOS_PACKAGE_IS_FRAMEWORK": "false"
    },
    "ipAddress": None,
    "version": "2017-01-16T15:48:18.007Z",
    "residency": None,
    "secrets": {},
    "taskKillGracePeriodSeconds": None,
    "unreachableStrategy": {
        "inactiveAfterSeconds": 900,
        "expungeAfterSeconds": 604800
    },
    "killSelection": "YOUNGEST_FIRST",
    "acceptedResourceRoles": [
        "*"
    ],
    "ports": [
        16000,
    ],
    "portDefinitions": [
        {
            "port": 16000,
            "protocol": "tcp",
            "labels": {}
        },
    ],
    "requirePorts": False,
    "versionInfo": {
        "lastScalingAt": "2017-01-16T15:48:18.007Z",
        "lastConfigChangeAt": "2017-01-16T15:48:18.007Z"
    },
    "tasksStaged": 0,
    "tasksRunning": 1,
    "tasksHealthy": 1,
    "tasksUnhealthy": 0,
    "deployments": [],
    "tasks": [
        {
            "ipAddresses": [
                {
                    "ipAddress": "127.0.0.1",
                    "protocol": "IPv4"
                }
            ],
            "stagedAt": "2017-01-16T15:48:18.463Z",
            "state": "TASK_RUNNING",
            "ports": [
                16000,
            ],
            "startedAt": "2017-01-16T15:48:42.061Z",
            "version": "2017-01-16T15:48:18.007Z",
            "id": "nginx.333d80f4-dc03-11e6-b993-e248be6c2f96",
            "appId": "/nginx-alwaysthere",
            "slaveId": "8ad5a85c-c14b-4cca-a089-b9dc006e7286-S0",
            "host": "127.0.0.1",
            "healthCheckResults": [
                {
                    "alive": True,
                    "consecutiveFailures": 0,
                    "firstSuccess": "2017-01-16T15:48:59.141Z",
                    "lastFailure": None,
                    "lastSuccess": "2017-01-16T15:48:59.141Z",
                    "lastFailureCause": None,
                    "instanceId": "nginx.marathon-333d80f4-dc03-11e6-b993-e248be6c2f96"
                }
            ]
        }
    ]
}

NGINX_APP_ENABLED = {
    "id": "/nginx-enabled",
    "cmd": ("cd /opt/bitnami/nginx && harpoon initialize nginx && "
            "rm -rf /opt/bitnami/nginx/html && ln -s "
            "/mnt/mesos/sandbox/hello-nginx-master/ /opt/bitnami/nginx/html "
            "&& harpoon start --foreground nginx"),
    "args": None,
    "user": None,
    "env": {},
    "instances": 1,
    "cpus": 1,
    "mem": 1024,
    "disk": 0,
    "gpus": 0,
    "executor": "",
    "constraints": [],
    "uris": [
        "https://github.com/mesosphere/hello-nginx/archive/master.zip"
    ],
    "fetch": [
        {
            "uri": "https://github.com/mesosphere/hello-nginx/archive/master.zip",
            "extract": True,
            "executable": False,
            "cache": False
        }
    ],
    "storeUrls": [],
    "backoffSeconds": 1,
    "backoffFactor": 1.15,
    "maxLaunchDelaySeconds": 3600,
    "container": {
        "type": "DOCKER",
        "volumes": [],
        "docker": {
            "image": "bitnami/nginx:1.10.2-r0",
            "network": "BRIDGE",
            "portMappings": [
                {
                    "containerPort": 80,
                    "hostPort": 0,
                    "servicePort": 10000,
                    "protocol": "tcp",
                    "labels": {}
                },
                {
                    "containerPort": 443,
                    "hostPort": 0,
                    "servicePort": 10001,
                    "protocol": "tcp",
                    "labels": {}
                }
            ],
            "privileged": False,
            "parameters": [],
            "forcePullImage": False
        }
    },
    "healthChecks": [
        {
            "gracePeriodSeconds": 300,
            "intervalSeconds": 60,
            "timeoutSeconds": 20,
            "maxConsecutiveFailures": 3,
            "delaySeconds": 15,
            "command": {
                "value": "harpoon status nginx | grep -q 'com.bitnami.nginx is running'"
            },
            "protocol": "COMMAND"
        }
    ],
    "readinessChecks": [],
    "dependencies": [],
    "upgradeStrategy": {
        "minimumHealthCapacity": 1,
        "maximumOverCapacity": 1
    },
    "labels": {
        "DCOS_PACKAGE_RELEASE": "5",
        "DCOS_SERVICE_SCHEME": "http",
        "DCOS_PACKAGE_SOURCE": "https://universe.mesosphere.com/repo",
        "DCOS_PACKAGE_METADATA": "blah, blah, bleh",
        "DCOS_PACKAGE_REGISTRY_VERSION": "2.0",
        "DCOS_SERVICE_NAME": "nginx-enabled",
        "DCOS_SERVICE_PORT_INDEX": "0",
        "DCOS_PACKAGE_VERSION": "1.10.2",
        "DCOS_PACKAGE_NAME": "nginx",
        "DCOS_PACKAGE_IS_FRAMEWORK": "false"
    },
    "ipAddress": None,
    "version": "2017-01-16T15:48:18.007Z",
    "residency": None,
    "secrets": {},
    "taskKillGracePeriodSeconds": None,
    "unreachableStrategy": {
        "inactiveAfterSeconds": 900,
        "expungeAfterSeconds": 604800
    },
    "killSelection": "YOUNGEST_FIRST",
    "acceptedResourceRoles": [
        "*"
    ],
    "ports": [
        16001,
    ],
    "portDefinitions": [
        {
            "port": 16001,
            "protocol": "tcp",
            "labels": {}
        },
    ],
    "requirePorts": False,
    "versionInfo": {
        "lastScalingAt": "2017-01-16T15:48:18.007Z",
        "lastConfigChangeAt": "2017-01-16T15:48:18.007Z"
    },
    "tasksStaged": 0,
    "tasksRunning": 1,
    "tasksHealthy": 1,
    "tasksUnhealthy": 0,
    "deployments": [],
    "tasks": [
        {
            "ipAddresses": [
                {
                    "ipAddress": "127.0.0.1",
                    "protocol": "IPv4"
                }
            ],
            "stagedAt": "2017-01-16T15:48:18.463Z",
            "state": "TASK_RUNNING",
            "ports": [
                16001,
            ],
            "startedAt": "2017-01-16T15:48:42.061Z",
            "version": "2017-01-16T15:48:18.007Z",
            "id": "nginx.333d80f4-dc03-11e6-b993-e248be6c2f96",
            "appId": "/nginx-enabled",
            "slaveId": "8ad5a85c-c14b-4cca-a089-b9dc006e7286-S0",
            "host": "127.0.0.1",
            "healthCheckResults": [
                {
                    "alive": True,
                    "consecutiveFailures": 0,
                    "firstSuccess": "2017-01-16T15:48:59.141Z",
                    "lastFailure": None,
                    "lastSuccess": "2017-01-16T15:48:59.141Z",
                    "lastFailureCause": None,
                    "instanceId": "nginx.marathon-333d80f4-dc03-11e6-b993-e248be6c2f96"
                }
            ]
        }
    ]
}


# pylint: disable=R0903
class MarathonHTTPRequestHandler(RecordingHTTPRequestHandler):
    """A very simple request handler that simply replies with static(empty) list
       of applications to the client

    Most probably it will be extended with some extra logic as tests are
    being added.
    """
    def _calculate_response(self, base_path, *_):
        """Reply with empty list of apps for the '/v2/apps' request

        Please refer to the description of the BaseHTTPRequestHandler class
        for details on the arguments and return value of this method.

        Raises:
            EndpointException: request URL path is unsupported
        """
        if base_path not in ['/v2/apps', "/v2/leader"]:
            msg = "Path `{}` is not supported yet".format(base_path)
            blob = msg.encode('utf-8')
            raise EndpointException(code=500, reason=blob)

        ctx = self.server.context

        with ctx.lock:
            if base_path == '/v2/apps':
                blob = self._convert_data_to_blob(ctx.data['endpoint-content'])
            elif base_path == '/v2/leader':
                if ctx.data['leader-content'] is None:
                    msg = "Marathon leader unknown"
                    blob = msg.encode('utf-8')
                    raise EndpointException(code=404, reason=blob)
                elif isinstance(ctx.data['leader-content'], str):
                    blob = ctx.data['leader-content'].encode('utf-8')
                    raise EndpointException(code=200, reason=blob)
                else:
                    blob = self._convert_data_to_blob(ctx.data['leader-content'])

        return blob


# pylint: disable=R0903,C0103
class MarathonEndpoint(RecordingTcpIpEndpoint):
    """An endpoint that mimics DC/OS root Marathon"""
    def __init__(self, port, ip=''):
        super().__init__(port, ip, MarathonHTTPRequestHandler)
        self._reset()

    def reset(self, *_):
        """Reset the endpoint to the default/initial state."""
        with self._context.lock:
            super().reset()
            self._reset()

    def enable_nginx_app(self, *_):
        """Change the endpoint output so that it simulates extra Nginx app
           running in the cluster
        """
        with self._context.lock:
            self._context.data["endpoint-content"]["apps"].append(NGINX_APP_ENABLED)

    def set_apps_response(self, apps):
        """Change the response content for apps endpoint"""
        with self._context.lock:
            self._context.data["endpoint-content"] = apps

    def remove_leader(self, *_):
        """Change the endpoint output so that it simulates absence of the Marathon
           leader node.
        """
        with self._context.lock:
            self._context.data["leader-content"] = None

    def change_leader(self, *_):
        """Change the endpoint output so that it responds with a non-default
           Marathon leader node.
        """
        with self._context.lock:
            self._context.data["leader-content"] = {"leader": "127.0.0.3:80"}

    def break_leader_reply(self, *_):
        """Change the endpoint output so that it responds with a broken
           reply to a query for Marathon leader node.
        """
        with self._context.lock:
            self._context.data["leader-content"] = 'blah blah buh buh'

    def _reset(self):
        """Reset internal state to default values"""
        self._context.data["endpoint-content"] = {"apps": [NGINX_APP_ALWAYSTHERE, ]}
        self._context.data["leader-content"] = {"leader": "127.0.0.2:80"}
