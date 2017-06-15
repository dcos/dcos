# Admin Ports

The following is a list of ports used by internal DC/OS services, and their corresponding systemd unit.

## All Roles

### TCP

 - 8053: dcos-net
 - 61053: dcos-mesos-dns
 - 61420: dcos-epmd
 - 62053: dcos-net
 - 62080: dcos-net
 - 62502: dcos-net

### UDP

 - 8053: dcos-net
 - 62053: dcos-net
 - 64000: dcos-net

## Master

### TCP

 - 53: dcos-net
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

 - 53: dcos-net

## Agent, Public Agent

### TCP

 - 5051: dcos-mesos-slave
 - 61001: dcos-adminrouter-agent
