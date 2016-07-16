#!/usr/bin/env python

import argparse
import logging
import os
import sys


from dcos_internal_utils import bootstrap
from dcos_internal_utils import exhibitor


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
    b.cluster_id('/var/lib/dcos/cluster-id')


@check_root
def dcos_signal(b, opts):
    b.cluster_id('/var/lib/dcos/cluster-id')


@check_root
def dcos_oauth(b, opts):
    b.generate_oauth_secret('/var/lib/dcos/dcos-oauth/auth-token-secret')


def noop(b, opts):
    return


bootstrappers = {
    'dcos-adminrouter': dcos_adminrouter,
    'dcos-signal': dcos_signal,
    'dcos-oauth': dcos_oauth,
    'dcos-3dt': noop,
    'dcos-marathon': noop,
    'dcos-mesos-master': noop,
    'dcos-cosmos': noop,
    'dcos-metronome': noop,
}


def main():
    opts = parse_args()

    logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')
    log.setLevel(logging.DEBUG)

    log.info('Clearing proxy environment variables')
    for name in ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY']:
        os.environ.pop(name, None)
        os.environ.pop(name.lower(), None)

    exhibitor.wait(opts.master_count)

    # The bootstrapper is lazily initialized because of Spartan
    # Spartan relies on bootstrap.py
    b = None

    for service in opts.services:
        if service not in bootstrappers:
            if opts.error_on_unknown:
                log.error('Unknown service: {}'.format(service))
                sys.exit(1)
            else:
                log.warning('Unknown service, not bootstrapping: {}'.format(service))
                continue
        if not b:
            b = bootstrap.Bootstrapper(opts.zk)
        log.debug('bootstrapping {}'.format(service))
        bootstrappers[service](b, opts)


def parse_args():
    if os.path.exists('/etc/mesosphere/roles/master'):
        zk_default = '127.0.0.1:2181'
    else:
        zk_default = 'mesos.mesos'

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
    parser.add_argument(
        '--error-on-unknown',
        action='store_true',
        dest='error_on_unknown',
        help='Error if bootstrapping unknown service')
    return parser.parse_args()
