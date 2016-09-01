#!/usr/bin/env python3
import argparse
from kazoo.client import KazooClient
from kazoo.handlers.threading import SequentialThreadingHandler
from kazoo.retry import KazooRetry

# Retry every .3 seconds for up to 1 second.
retry_policy = KazooRetry(
    max_tries=3,
    delay=0.3,
    backoff=1,
    max_jitter=0.1,
    max_delay=1)

parser = argparse.ArgumentParser()
parser.add_argument('email')
parser.add_argument('--zk', default='127.0.0.1:2181')

args = parser.parse_args()
email = args.email

zk = KazooClient(
    hosts=args.zk,
    timeout=1.0,
    handler=SequentialThreadingHandler(),
    connection_retry=retry_policy,
    command_retry=retry_policy)
zk.start()
zk.ensure_path("/dcos/users/")
zk.create("/dcos/users/{}".format(email), email.encode())
