#!/usr/bin/env python3
import argparse
import sys

from kazoo.client import KazooClient
from kazoo.exceptions import NodeExistsError, NoNodeException
from kazoo.handlers.threading import SequentialThreadingHandler
from kazoo.retry import KazooRetry


def _error(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


# Retry every .3 seconds for up to 1 second.
retry_policy = KazooRetry(
    max_tries=3,
    delay=0.3,
    backoff=1,
    max_jitter=0.1,
    max_delay=1)

parser = argparse.ArgumentParser()
parser.add_argument('email')
parser.add_argument('--zk', default='zk-1.zk:2181,zk-2.zk:2181,zk-3.zk:2181,zk-4.zk:2181,zk-5.zk:2181')

args = parser.parse_args()
email = args.email
zk_host = args.zk

zk = KazooClient(
    hosts=zk_host,
    timeout=1.0,
    handler=SequentialThreadingHandler(),
    connection_retry=retry_policy,
    command_retry=retry_policy)
try:
    zk.start()
    zk.ensure_path("/dcos/users/")
    zk.create("/dcos/users/{}".format(email), email.encode())
    print("User {} successfully added".format(email), file=sys.stdout)
    sys.exit(0)
except zk.handler.timeout_exception:
    _error("Timeout connecting to {}".format(zk_host))
except NoNodeException:
    _error("Unable to create base node /dcos/users/")
except NodeExistsError:
    _error("User {} already exists".format(email))
