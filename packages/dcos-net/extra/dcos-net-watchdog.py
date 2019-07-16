#!/opt/mesosphere/bin/python

import logging
import os
import subprocess
import sys
import time

import dns.query


WATCHDOG_TIMEOUT = 60
NAME_SERVERS = ['198.51.100.1', '198.51.100.2', '198.51.100.3']
DNS_QUERY = 'ready.spartan'
DNS_TIMEOUT = 5
SERVICE = 'dcos-net.service'


def watchdog(ns):
    try:
        logging.info('Sending DNS query: %s', ns)
        query = dns.message.make_query(DNS_QUERY, dns.rdatatype.ANY)
        result = dns.query.udp(query, ns, DNS_TIMEOUT)
        for rr in result.answer:
            logging.info('%s', rr)
        if not result.answer:
            logging.error('Host not found')
        else:
            logging.info('%s is healthy', SERVICE)
        return result.answer != []
    except dns.exception.Timeout:
        logging.error('DNS Server Timeout')
    except:
        logging.error('Exception: {}'.sys.exc_info()[1])
    return False


def kill(name):
    if os.getenv('DCOS_NET_WATCHDOG') == 'false':
        logging.info('Killing is disabled')
        return 0
    logging.info('Killing %s', name)
    r = subprocess.run(['/usr/bin/env',
                        'systemctl', 'kill',
                        '--signal', 'SIGKILL',
                        '--kill-who', 'main',
                        name])
    if r.returncode == 0:
        logging.info('%s was successfully killed', name)
    return r.returncode


def sleep(secs):
    logging.info('Sleeping for %i seconds', secs)
    time.sleep(secs)


def loop():
    for ns in NAME_SERVERS:
        if watchdog(ns):
            return 0
    sleep(WATCHDOG_TIMEOUT)
    for ns in NAME_SERVERS:
        if watchdog(ns):
            return 0
    return kill(SERVICE)


def main():
    logging.basicConfig(
        stream=sys.stdout, level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='')
    while True:
        loop()
        sleep(WATCHDOG_TIMEOUT)


if __name__ == '__main__':
    main()
