# Admin Ports

The following is a list of ports used by internal DC/OS services, and their corresponding systemd unit.

## All Roles

### TCP

 - 61003: dcos-rexray (default)
 - 61053: dcos-mesos-dns
 - 61420: dcos-epmd
 - 61421: dcos-minuteman
 - 62053: dcos-spartan
 - 62080: dcos-navstar
 - 62501: dcos-spartan
 - 62502: dcos-navstar
 - 62503: dcos-minuteman

### UDP

 - 62053: dcos-spartan
 - 64000: dcos-navstar

## Master

### TCP

 - 53: dcos-spartan
 - 80: dcos-adminrouter
 - 443: dcos-adminrouter
 - 1050: dcos-3dt
 - 1801: dcos-oauth
 - 2181: dcos-exhibitor
 - 2888: dcos-exhibitor
 - 3888: dcos-exhibitor
 - 5050: dcos-mesos-master
 - 7070: dcos-cosmos
 - 8080: dcos-marathon
 - 8123: dcos-mesos-dns
 - 8181: dcos-exhibitor
 - 9990: dcos-cosmos
 - 15055: dcos-history-service
 - 15101: dcos-marathon libprocess
 - 15201: dcos-metronome libprocess

### UDP

 - 53: dcos-spartan

## Agent, Public Agent

### TCP

 - 5051: dcos-mesos-slave
 - 61001: dcos-adminrouter-agent
