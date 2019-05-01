#!/usr/bin/env python

import argparse
import json
import logging
import os
import random
import sys

from dcos_internal_utils import bootstrap
from dcos_internal_utils import exhibitor

from pkgpanda.actions import apply_service_configuration

log = logging.getLogger(__name__)


def check_root(fun):
    def wrapper(b, opts):
        if os.getuid() != 0:
            log.error('bootstrap must be run as root')
            sys.exit(1)
        fun(b, opts)
    return wrapper


@check_root
def dcos_adminrouter(b, opts):
    b.cluster_id()


@check_root
def dcos_signal(b, opts):
    b.cluster_id()


@check_root
def dcos_telegraf_master(b, opts):
    b.cluster_id()


@check_root
def dcos_telegraf_agent(b, opts):
    b.cluster_id(readonly=True)


@check_root
def dcos_net(b, opts):
    if 'master' in get_roles():
        dcos_net_master(b, opts)
    else:
        dcos_net_agent(b, opts)


@check_root
def dcos_net_master(b, opts):
    b.cluster_id()


@check_root
def dcos_net_agent(b, opts):
    b.cluster_id(readonly=True)


@check_root
def dcos_oauth(b, opts):
    b.generate_oauth_secret('/var/lib/dcos/dcos-oauth/auth-token-secret')


@check_root
def dcos_bouncer(b, opts):
    os.makedirs('/run/dcos/dcos-bouncer', exist_ok=True)
    shutil.chown('/run/dcos/dcos-bouncer', user='dcos_bouncer')
    # Permissions are restricted to the dcos_bouncer user as this directory
    # contains sensitive data.  See
    # https://jira.mesosphere.com/browse/DCOS-18350

    # The ``bouncer_tmpdir`` directory path corresponds to the
    # TMPDIR environment variable configured in the dcos-bouncer.service file.
    user = 'dcos_bouncer'
    bouncer_tmpdir = known_exec_directory() / user
    bouncer_tmpdir.mkdir(mode=0o700, exist_ok=True)
    shutil.chown(str(bouncer_tmpdir), user=user)


@check_root
def dcos_history(b, opts):
    # Permissions are restricted to the dcos_history user in case this
    # directory contains sensitive data - we also want to avoid the security
    # risk of other users writing to this directory.
    # See https://jira.mesosphere.com/browse/DCOS-18350 for a related change to
    # dcos-bouncer.

    # The ``dcos_history_tmpdir`` directory path corresponds to the
    # TMPDIR environment variable configured in the dcos-history.service file.
    user = 'dcos_history'
    dcos_history_tmpdir = known_exec_directory() / user
    dcos_history_tmpdir.mkdir(mode=0o700, exist_ok=True)
    shutil.chown(str(dcos_history_tmpdir), user=user)


def noop(b, opts):
    return


bootstrappers = {
    'dcos-adminrouter': dcos_adminrouter,
    'dcos-signal': dcos_signal,
    'dcos-oauth': dcos_oauth,
    'dcos-diagnostics-master': noop,
    'dcos-diagnostics-agent': noop,
    'dcos-checks-master': noop,
    'dcos-checks-agent': noop,
    'dcos-marathon': noop,
    'dcos-mesos-master': noop,
    'dcos-mesos-slave': noop,
    'dcos-mesos-slave-public': noop,
    'dcos-cosmos': noop,
    'dcos-cockroach': noop,
    'dcos-metronome': noop,
    'dcos-history': noop,
    'dcos-mesos-dns': noop,
    'dcos-net': dcos_net,
    'dcos-telegraf-master': dcos_telegraf_master,
    'dcos-telegraf-agent': dcos_telegraf_agent,
}


def get_roles():
    return os.listdir('/opt/mesosphere/etc/roles')


def main():
    opts = parse_args()

    # Display the pid in each log message to distinguish concurrent runs
    log_format = 'pid={}:[%(levelname)s] %(message)s'.format(os.getpid())
    logging.basicConfig(format=log_format, level='INFO')
    logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')
    log.setLevel(logging.DEBUG)

    log.info('Clearing proxy environment variables')
    for name in ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY']:
        os.environ.pop(name, None)
        os.environ.pop(name.lower(), None)

    if 'master' in get_roles():
        exhibitor.wait(opts.master_count)

    b = bootstrap.Bootstrapper(opts.zk)

    for service in opts.services:
        if service not in bootstrappers:
            log.info('Unknown service: {}'.format(service))
            sys.exit(1)
        apply_service_configuration(service)
        log.debug('bootstrapping {}'.format(service))
        bootstrappers[service](b, opts)


def get_zookeeper_address_agent():
    if os.getenv('MASTER_SOURCE') == 'master_list':
        # dcos-net agents with static master list
        with open('/opt/mesosphere/etc/master_list', 'r') as f:
            master_list = json.load(f)
        assert len(master_list) > 0
        return random.choice(master_list) + ':2181'
    elif os.getenv('EXHIBITOR_ADDRESS'):
        # dcos-net agents on AWS
        return os.getenv('EXHIBITOR_ADDRESS') + ':2181'
    else:
        # any other agent service
        return 'zk-1.zk:2181,zk-2.zk:2181,zk-3.zk:2181,zk-4.zk:2181,zk-5.zk:2181'


def get_zookeeper_address():
    # Masters use a special zk address since dcos-net and the like aren't up yet.
    roles = get_roles()
    if 'master' in roles:
        return '127.0.0.1:2181'

    if 'slave' in roles or 'slave_public' in roles:
        return get_zookeeper_address_agent()

    raise Exception("Can't get zookeeper address. Unknown role: {}".format(roles))


def parse_args():
    zk_default = get_zookeeper_address()

    parser = argparse.ArgumentParser()
    parser.add_argument('services', nargs='+')
    parser.add_argument(
        '--zk',
        type=str,
        default=zk_default,
        help='Host string passed to Kazoo client constructor.')
    parser.add_argument(
        '--master_count',
        type=str,
        default='/opt/mesosphere/etc/master_count',
        help='File with number of master servers')
    return parser.parse_args()
