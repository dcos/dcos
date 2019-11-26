## Overview

This package provides etcd service for DC/OS.

etcd is an open-source distributed key-value store, aiming to provide a highly reliable and consistent way for data storage.

## Why we need etcd

Despite the existing key/value storage in DC/OS, like Zookeeper, etcd is still introduced to support Calico in DC/OS, which works with either Kubernetes or etcd as the datastore.

## How etcd works

etcd cluster will be deployed on all master nodes for high availability, and node discovery of etcd is achieved by reporting the node addresses to Zookeeper during the stage of bootstrap.

etcd cluster is exposed outside by DNS-based endpoints, like `master.dcos.thisdcos.directory:2379`.

