"""
exhibitor-migrate
=================
When a user is updating to DC/OS 1.9 from an older version we need to update several values in exhibitor to use the new
filesystem paths for zookeeper state on disk.
"""
import argparse
import copy
import sys

import requests
from requests import RequestException

DESCRIPTION_STATUS = """
Will query exhibitor (at `localhost`) and check if the migration has been completed, in progress, or has not yet been
performed.

| exit code | State                                                                         |
| --------- | ----------------------------------------------------------------------------- |
| 0         | Exhibitor has new expected values and no rollout is in progress               |
| 1         | IO Error when trying to connect to exhibitor (expected if run on an agent)    |
| 2         | Error when reading from exhibitor (Any response other than 200)               |
| 4         | Rolling update in progress                                                    |
| 8         | At least one config value does not have the expected post migration value     |


This script can be run on any of the DC/OS Master nodes by running (as root)

```
dcos-shell dcos-exhibitor-migrate-status [--username username --password password]
```
"""  # noqa

DESCRIPTION_PERFORM = """
Will attempt to update the exhibitor (at `localhost`) config and trigger a rolling update .

| exit code | State                                                                                                                 |
| --------- | --------------------------------------------------------------------------------------------------------------------- |
| 0         | Exhibitor has new expected values OR Has successfully triggered the rolling update                                    |
| 1         | IO Error when trying to connect to exhibitor (expected if run on an agent)                                            |
| 2         | Error when reading from exhibitor (Any response other than 200)                                                       |
| 4         | Rolling update in progress                                                                                            |
| 8         | At least one config value does not have the expected pre migration value, and automatic migration can not take place  |
| 16        | Attempting to start the rolling update failed due to a non 200 response from exhibitor                                |


This script can be run on any of the DC/OS Master nodes by running (as root)

```
dcos-shell dcos-exhibitor-migrate-perform [--username username --password password]
```
"""  # noqa

ZOOKEEPER_DATA_DIR_START = '/var/lib/zookeeper/snapshot'
ZOOKEEPER_LOG_DIR_START = '/var/lib/zookeeper/transactions'
LOG_INDEX_DIR_START = '/var/lib/zookeeper/transactions'

ZOOKEEPER_DATA_DIR_GOAL = '/var/lib/dcos/exhibitor/zookeeper/snapshot'
ZOOKEEPER_LOG_DIR_GOAL = '/var/lib/dcos/exhibitor/zookeeper/transactions'
LOG_INDEX_DIR_GOAL = '/var/lib/dcos/exhibitor/zookeeper/transactions'


class ValidationError(Exception):
    def __init__(self, msg, exit_status=8):
        self.msg = msg
        self.exit_status = exit_status


def get_config_json(response):
    if response.status_code == 200 and response.headers['Content-Type'].startswith('application/json'):
        json = response.json()
        if 'config' not in json:
            raise ValidationError(".config property not present in exhibitor response. {}".format(response.json()), 2)
        return json['config']
    else:
        raise ValidationError("Error reading configuration from Exhibitor. {} {}"
                              .format(response.status_code, response.content), 2)


def migration_already_complete(config):
    if config['rollInProgress'] is True:
        return False
    else:
        return (config['zookeeperDataDirectory'] == ZOOKEEPER_DATA_DIR_GOAL and
                config['zookeeperLogDirectory'] == ZOOKEEPER_LOG_DIR_GOAL and
                config['logIndexDirectory'] == LOG_INDEX_DIR_GOAL)


def assert_can_migrate(config):
    if config['rollInProgress'] is True:
        raise ValidationError("Rolling upgrade in progress. {}".format(config['rollStatus']), 4)
    else:
        validate_config_key("ZooKeeper Data Directory", ZOOKEEPER_DATA_DIR_START, config['zookeeperDataDirectory'])
        validate_config_key("ZooKeeper Log Directory", ZOOKEEPER_LOG_DIR_START, config['zookeeperLogDirectory'])
        validate_config_key("Log Index Directory", LOG_INDEX_DIR_START, config['logIndexDirectory'])


def validate_config(config):
    if config['rollInProgress'] is True:
        raise ValidationError("Rolling update in progress. {}".format(config['rollStatus']), 4)
    else:
        validate_config_key("ZooKeeper Data Directory", ZOOKEEPER_DATA_DIR_GOAL, config['zookeeperDataDirectory'])
        validate_config_key("ZooKeeper Log Directory", ZOOKEEPER_LOG_DIR_GOAL, config['zookeeperLogDirectory'])
        validate_config_key("Log Index Directory", LOG_INDEX_DIR_GOAL, config['logIndexDirectory'])


def validate_config_key(pretty_name, expected, actual):
    if actual != expected:
        raise ValidationError("{} does not match expected value. expected: {} actual: {}"
                              .format(pretty_name, expected, actual))


def update_config(current_config):
    config = copy.deepcopy(current_config)
    config['zookeeperDataDirectory'] = ZOOKEEPER_DATA_DIR_GOAL
    config['zookeeperLogDirectory'] = ZOOKEEPER_LOG_DIR_GOAL
    config['logIndexDirectory'] = LOG_INDEX_DIR_GOAL
    return config


def parse_args(description: str):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--username', help="Username for Exhibitor's HTTP basic auth")
    parser.add_argument('--password', help="Password for Exhibitor's HTTP basic auth")
    args = parser.parse_args()

    auth_args_provided = [arg is not None for arg in [args.username, args.password]]
    if any(auth_args_provided) and not all(auth_args_provided):
        parser.error('If either --username or --password is passed, both must be passed')

    return args


def auth_from_args(args):
    if args.username is None:
        return None
    else:
        return (args.username, args.password)


def perform():
    args = parse_args(DESCRIPTION_PERFORM)
    auth = auth_from_args(args)
    try:
        resp = requests.get("http://127.0.0.1:8181/exhibitor/v1/config/get-state", auth=auth, timeout=(3, 10))
        config = get_config_json(resp)
        if migration_already_complete(config):
            print("Migration already complete")
            sys.exit(0)
        else:
            assert_can_migrate(config)
            updated_config = update_config(config)
            set_rolling_response = requests.post("http://localhost:8181/exhibitor/v1/config/set-rolling",
                                                 json=updated_config, timeout=(3, 10))
            if set_rolling_response.status_code == 200:
                print("Rolling update started")
                sys.exit(0)
            else:
                print("Failed to start rolling update: {}".format(set_rolling_response))
                sys.exit(16)

    except ValidationError as ve:
        print(ve.msg)
        sys.exit(ve.exit_status)
    except RequestException as mre:
        print(mre)
        sys.exit(1)


def status():
    args = parse_args(DESCRIPTION_STATUS)
    auth = auth_from_args(args)
    try:
        resp = requests.get("http://127.0.0.1:8181/exhibitor/v1/config/get-state", auth=auth, timeout=(3, 10))
        config = get_config_json(resp)
        validate_config(config)
    except ValidationError as ve:
        print(ve.msg)
        sys.exit(ve.exit_status)
    except RequestException as mre:
        print(mre)
        sys.exit(1)
