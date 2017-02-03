#!/bin/bash -xe

export GOPATH=/pkg:$GOPATH
export PATH=/pkg/bin:$PATH

mkdir -p /pkg/src/github.com/mesosphere
mv /pkg/src/mesos-dns /pkg/src/github.com/mesosphere/
cd /pkg/src/github.com/mesosphere/mesos-dns
go install -v ./...

mkdir -p $PKG_PATH/bin
cp -v /pkg/bin/mesos-dns $PKG_PATH/bin

# Create the service file
service="$PKG_PATH/dcos.target.wants_master/dcos-mesos-dns.service"
mkdir -p "$(dirname "$service")"
cp /pkg/extra/dcos-mesos-dns.service "$service"
