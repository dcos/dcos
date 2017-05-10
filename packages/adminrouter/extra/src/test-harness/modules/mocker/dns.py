# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""
Programmable in-memory DNS server
"""

import logging

from dnslib import QTYPE, RCODE, RR
from dnslib.server import BaseResolver, DNSLogger, DNSServer

log = logging.getLogger(__name__)

DEFAULT_LEADER_ADDR = "127.0.0.2"
DEFAULT_MASTER_ADDR = "127.0.0.1"
DEFAULT_AGENT_ADDR = "127.0.0.1"
DEFAULT_SLAVE_ADDR = "127.0.0.1"
DEFAULT_TTL = 60


class DcosDnsResolver(BaseResolver):
    def reset(self):
        self._records = {
            "leader.mesos.": {
                "ip": DEFAULT_LEADER_ADDR,
                "ttl": DEFAULT_TTL,
            },
            "master.mesos.": {
                "ip": DEFAULT_MASTER_ADDR,
                "ttl": DEFAULT_TTL,
            },
            "agent.mesos.": {
                "ip": DEFAULT_AGENT_ADDR,
                "ttl": DEFAULT_TTL,
            },
            "slave.mesos.": {
                "ip": DEFAULT_SLAVE_ADDR,
                "ttl": DEFAULT_TTL,
            },
        }

    def __init__(self):
        super().__init__()
        self.reset()

    def resolve(self, request, handler):
        reply = request.reply()

        if request.q.qtype != QTYPE.A:
            log.error("Unsupported query qtype: `{}`".format(request.q.qtype))
            reply.header.rcode = getattr(RCODE, 'NXDOMAIN')
            return reply

        query = str(request.q.qname)
        if query not in self._records:
            log.error("qname `{}` not present in DB".format(query))
            reply.header.rcode = getattr(RCODE, 'NXDOMAIN')
            return reply

        log.info(
            "DNS query for `{}`, type `{}`".format(query, request.q.qtype))

        reply.add_answer(
            *RR.fromZone("{} {} A {}".format(
                query,
                self._records[query]['ttl'],
                self._records[query]['ip'],
                )
            )
        )

        return reply

    def set_dns_entry(self, name, ip=None, ttl=None):
        if name not in self._records:
            assert ip is not None
            if ttl is None:
                ttl = DEFAULT_TTL

            self._records[name] = {"ip": ip, "ttl": ttl}
            return

        if ip is not None:
            self._records[name]["ip"] = ip

        if ttl is not None:
            self._records[name]["ttl"] = ttl

    def remove_dns_entry(self, name):
        assert name in self._records
        del self._records[name]


class DcosDnsServer:
    """Simple DNS server that responds to *.mesos DNS queries"""

    def __init__(self, server_addresses):
        self._servers = []
        for sa in server_addresses:
            self._servers.append(
                DNSServer(
                    resolver=DcosDnsResolver(),
                    address=sa[0],
                    port=sa[1],
                    logger=DNSLogger("pass"),  # Don't log anything to stdout
                    )
            )

    def start(self):
        for s in self._servers:
            s.start_thread()

    def stop(self):
        for s in self._servers:
            s.stop()

    def reset(self):
        for s in self._servers:
            s.server.resolver.reset()

    def set_dns_entry(self, name, ip=None, ttl=None):
        for s in self._servers:
            s.server.resolver.set_dns_entry(name, ip, ttl)

    def remove_dns_entry(self, name):
        for s in self._servers:
            s.server.resolver.remove_dns_entry(name)
