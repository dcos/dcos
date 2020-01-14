## Overview

This package provides DC/OS Calico component to support Calico networking containers and network policy in DC/OS.

## system requirements

### Network requirements

| Port | DC/OS Component | systemd Unit             | Source       | Destination  | Description                                                                                                                         |
|------|-----------------|--------------------------|--------------|--------------|-------------------------------------------------------------------------------------------------------------------------------------|
| 179  | Calico          | dcos-calico-bird.service | agent/master | agent/master | calico BGP networking                                                                                                               |
| 2379 | etcd            | dcos-etcd.service        | agent/master | agent/master | etcd requires this port to be open between masters for leader election and peering connections when using standalone etcd (clustered). |
| 2380 | etcd            | dcos-etcd.service        | master       | master       | etcd requires this port to be open between masters for leader election and peering connections when using standalone etcd              |
| 64000 | Calico          | dcos-calico-felix.service | agent/master | agent/master | (Configurable) calico VXLAN networking can be configurable by calico_vxlan_port, by default, this shares the same value with dcos overlay vxlan port  |
| 62091 | Calico          | dcos-calico-felix.service | agent/master | agent/master | TCP port that the Prometheus metrics server should bind to                                                                   |

## DC/OS Calico component

DC/OS Calico component integrates the [Calico networking](https://www.projectcalico.org) into DC/OS, by providing Calico CNI plugin for Mesos Universal Container Runtime, besides, the calico control panel will provide the functionality of network policy for DC/OS workloads.

### DC/OS Calico services

DC/OS Calico integrates Calico into DC/OS for managing container networking and network security, three services are introduced:
- dcos-calico-bird.service: A BGP client that exchanges routing information between hosts for Calico. [source](https://github.com/projectcalico/bird)
- dcos-calico-confd.service: The confd templating engine monitors etcd datastores and generating and reloading bird configuration dynamically. [source](https://github.com/projectcalico/node)
- dcos-calico-felix.service: the control panel for Calico networking to program routes and ACL's for containers. [source](https://github.com/projectcalico/node)

## Configuration Reference(Networking)

| Parameter            | Description                                                                                                                        |
|----------------------|------------------------------------------------------------------------------------------------------------------------------------|
| calico_network_cidr  | Subnet allocated for calico. The subnet specified by `calico_network_cidr` should not overlap with those for VXLAN backends or virtual networks defined for [DC/OS virtual networks](https://github.com/mesosphere/dcos-docs-site/blob/staging/pages/mesosphere/dcos/1.14/installing/production/advanced-configuration/configuration-reference/index.md#dcos_overlay_enable). Default: '192.168.0.0/16']                                                                          |
| calico_vxlan_enabled | Control, whether IP-in-IP or VXLAN mode is used for calico, by default IP-in-IP, is suggested to be used instead of VXLAN. `calico_vxlan_enabled` is supposed to set to 'true' for the environment that IP in IP is not supported, like Azure. [Default: 'false']    |
| calico_ipinip_mtu    | The MTU to set on the Calico IPIP tunnel device. This configuration works when calico_vxlan_enabled is set to be false. Please refer to [this](https://docs.projectcalico.org/v3.8/networking/mtu) for a suitable MTU configuration. [Default: 1440]    |
| calico_vxlan_port    | The UDP port used for calico VXLAN. This configuration works when calico_vxlan_enabled is set to be true. [Default: 4789]           |
| calico_vxlan_vni     | The virtual network ID used for calico VXLAN. This configuration works when calico_vxlan_enabled is set to be true. [Default: 4096] |
| calico_vxlan_mtu     | The MTU to set on the Calico VXLAN tunnel device. This configuration works when calico_vxlan_enabled is set to be true. Please refer to [this](https://docs.projectcalico.org/v3.8/networking/mtu) for a suitable MTU configuration [Default: 1410]    |
| calico_veth_mtu     | The MTU to set on the veth pair devices, e.g. both the container interface and host-end interface. Please refer to [this](https://docs.projectcalico.org/v3.8/networking/mtu) for a suitable MTU configuration [Default: 1410]    |

## Network Policy

Network policy provides the ability to control network traffic by an ordered set of rules applied to the endpoints specified by a label selector, please refer [here](https://docs.projectcalico.org/v3.8/reference/resources/networkpolicy) for a detailed explanation of policy rule definitions and label selector syntax.

In DC/OS, Calico network policy is exposed directly to the operators, so that the operator can manage their traffic control according to different scenarios.

limitations on network policy we have in DC/OS:
- Calico network policy is a namespaced resource, but for now, we support only `default` namespace in DC/OS, and all the namespaced Calico resources should be defined under `default` namespace.
- Calico network policy takes effect only on Calico networking containers, which means labels set on non-Calico networking containers like `hostnetwork`, `dcos` and `bridge` will not count in Calico network policy.
- Labels work for network policy MUST be set in NetworkInfo.Labels in Mesos, and for Marathon, they should be in networks.Labels, for example:
```
{
  "id": "/client",
  "instances": 1,
  "container": {
    "type": "MESOS",
    "volumes": [],
    "docker": {
      "image": "mesosphere/id-server:2.1.0"
    },
    "portMappings": []
  },
  "cpus": 0.1,
  "mem": 128,
  "requirePorts": false,
  "networks": [
    {
      "mode": "container",
      "name": "calico",
      "labels": {
        "role": "client"
      }
    }
  ],
  "healthChecks": [],
  "fetch": [],
  "constraints": []
}
```

### default profile

Calico Profile groups endpoints which inherit labels defined in the profile, for example, each namespace has one corresponding profile to granting labels to Pods in the namespace. Calico profile supports policy rules for traffic control but is deprecated in favor of much more flexible NetworkPolicy and GlobalNetworkPolicy resources.

In our case, all Calico networking containers will be assigned with a default profile with the same name as CNI network, `calico` by default, and this profile allows **only** requests from one Calico container network to another one,  which means L4LB and L7 proxy requests in which the source IP address is NATed to that of tunnel interfaces generated by Calico, and finally will be dropped. This profile can found in the following YAML definition.
```yaml
apiVersion: projectcalico.org/v3
kind: Profile
metadata:
  creationTimestamp: 2019-12-23T04:16:55Z
  name: calico
  resourceVersion: "75"
  uid: 0e105ecb-253b-11ea-9e52-065b6833052c
spec:
  egress:
  - action: Allow
    destination: {}
    source: {}
  ingress:
  - action: Allow
    destination: {}
    source:
      selector: has(calico)
  labelsToApply:
    calico: ""
```
To resolve this problem, calico profile `calico` is initialized by default by `dcos-calico-felix`, and allows all traffic into and out of Calico networking containers, and `calico` is the only profile supported for now and shared across all Calico networking containers.
For a more detailed description of the Calico profile, please read [here](https://docs.projectcalico.org/v3.8/reference/resources/profile).

## Example

### Calico networking containers

To use Calico networking containers, you only have to specify the network name as `calico`, and the following example shows the Marathon application definition of Calico networking containers supported by Mesos UCR.
a Marathon application with Calcico networking supported by Mesos UCR:
```
{
  "id": "/calico-ucr",
  "instances": 1,
  "container": {
    "type": "MESOS",
    "volumes": [],
    "docker": {
      "image": "mesosphere/id-server:2.1.0"
    },
    "portMappings": []
  },
  "cpus": 0.1,
  "mem": 128,
  "requirePorts": false,
  "networks": [
    {
      "mode": "container",
      "name": "calico"
    }
  ],
  "healthChecks": [],
  "fetch": [],
  "constraints": []
}
```

TODO: Or you could create a Calico networking Service through DC/OS web interface, tracked in [DCOS-62535](https://jira.mesosphere.com/browse/DCOS-62535)

### Network policy examples

In the following business isolation example,  we have three application definitions as shown below, and both bookstore-frontend and bookstore-server are labeled with `"biz_type": "bookstore"`, while fruitstore-frontend is labeled with `"biz_type": "fruitstore"`. Here we will create a network policy to deny the requests from fruitstore-frontend to bookstore-server while allow requests from bookstore-frontend to bookstore-server.
```
+----------------------+      +------------------------+
|                      |      |                        |
|  bookstore-frontend  |      |   fruitstore-frontend  |
|                      |      |                        |
+-----------------+----+      +----+-------------------+
                  |                |
                  |                |
                  |                x
                  |                |
             +----v----------------v--+
             |                        |
             |   bookstore-server     |
             |                        |
             +------------------------+
```

#### Launch Marathon applications

The Marathon application definition of bookstore-frontend with policy label `"biz_type": "bookstore"`:
```
{
  "id": "/bookstore-frontend",
  "instances": 1,
  "container": {
    "type": "MESOS",
    "volumes": [],
    "docker": {
      "image": "mesosphere/id-server:2.1.0"
    },
    "portMappings": []
  },
  "cpus": 0.1,
  "mem": 128,
  "requirePorts": false,
  "networks": [
    {
      "mode": "container",
      "name": "calico",
      "labels": {
        "biz_type": "bookstore"
      }
    }
  ],
  "healthChecks": [],
  "fetch": [],
  "constraints": []
}
```
The Marathon application definition of bookstore-server with policy label `"biz_type": "bookstore"` and `"role": "server"`, available on port 80:

```
{
  "id": "/bookstore-server",
  "instances": 1,
  "container": {
    "type": "MESOS",
    "volumes": [],
    "docker": {
      "image": "mesosphere/id-server:2.1.0"
    },
    "portMappings": []
  },
  "cpus": 0.1,
  "mem": 128,
  "requirePorts": false,
  "networks": [
    {
      "mode": "container",
      "name": "calico",
      "labels": {
        "biz_type": "bookstore",
        "role": "server"
      }
    }
  ],
  "healthChecks": [],
  "fetch": [],
  "constraints": []
}
```
The Marathon application definition of fruitstore-frontend with policy label `"biz_type": "fruitstore"`:
```
{
  "id": "/fruitstore-frontend",
  "instances": 1,
  "container": {
    "type": "MESOS",
    "volumes": [],
    "docker": {
      "image": "mesosphere/id-server:2.1.0"
    },
    "portMappings": []
  },
  "cpus": 0.1,
  "mem": 128,
  "requirePorts": false,
  "networks": [
    {
      "mode": "container",
      "name": "calico",
      "labels": {
        "biz_type": "fruitstore"
      }
    }
  ],
  "healthChecks": [],
  "fetch": [],
  "constraints": []
}
```
Lauch the above three Marathon applications by executing `dcos marathon app add ${app_definition_yaml_file}`, and we will then obtain three running Marathon applications as show below:
```
$ dcos task list
         NAME              HOST      USER     STATE                                         ID                                                    AGENT ID                  REGION  ZONE
  fruitstore-frontend  172.16.2.233  root  TASK_RUNNING  fruitstore-frontend.instance-8a3ed6db-2a47-11ea-91b3-66db602e14f5._app.1  0a1399a2-fe1f-4613-a618-f45159e12f2a-S0  N/A     N/A
  bookstore-server     172.16.29.45  root  TASK_RUNNING  bookstore-server.instance-825bcbda-2a47-11ea-91b3-66db602e14f5._app.1     0a1399a2-fe1f-4613-a618-f45159e12f2a-S1  N/A     N/A
  bookstore-frontend   172.16.2.233  root  TASK_RUNNING  bookstore-frontend.instance-79853919-2a47-11ea-91b3-66db602e14f5._app.1   0a1399a2-fe1f-4613-a618-f45159e12f2a-S0  N/A     N/A
```

#### Test the connectivity between the frontends and the server

Before applying network policy, the requests from bookstore-frontend and fruitstore-frontend to bookstore-server are successful, here we expect the FQDN `bookstore-server.marathon.containerip.dcos.thisdcos.directory` to return the bookstore-server container IP address:
```
$ dcos task exec fruitstore-frontend wget -qO- bookstore-server.marathon.containerip.dcos.thisdcos.directory:80/id
hubfeu2yculh%

$ dcos task exec bookstore-frontend wget -qO- bookstore-server.marathon.containerip.dcos.thisdcos.directory:80/id
hubfeu2yculh%
```

#### Apply network policy

This network policy takes effect on bookstore-server and allows requests from applications with label `biz_type` set as `bookstore` while rejects those from applications with label `biz_type` set as `fruitstore`:
```
apiVersion: projectcalico.org/v3
kind: NetworkPolicy
metadata:
  name: allow-bookstore-cliient-to-server
spec:
  selector: biz_type == 'bookstore' && role == 'server'
  types:
  - Ingress
  ingress:
  - action: Allow
    protocol: TCP
    source:
      selector:  biz_type == 'bookstore'
    destination:
      ports:
      - 80
  - action: Deny
    protocol: TCP
    source:
      selector: biz_type == 'fruitstore'
    destination:
      ports:
      - 80
```
Temporarily, we can log into a DC/OS node, and apply the network policy by executing `/opt/mesosphere/bin/calicoctl apply -f ${network_policy_yaml_file}`.

TODO: We need to change the above action by applying the network policy outside of the DC/OS cluster through dcos CLI, which is tracked in https://jira.mesosphere.com/browse/DCOS-59091

Request from bookstore-frontend is successful as expected:
```
$ dcos task exec bookstore-frontend wget -qO- bookstore-server.marathon.containerip.dcos.thisdcos.directory:80/id
hubfeu2yculh%
```
Request from fruitstore-frontend is timed out for packets are dropped.
```
$ dcos task exec fruitstore-frontend wget -qO- --timeout=5 bookstore-server.marathon.containerip.dcos.thisdcos.directory:80/id
wget: can't connect to remote host (192.168.219.133): Connection timed out
```

## Troubleshoot

Diagnostic info including Calico resources, components logs, and BGP peer status are collected in DC/OS node diagnostic bundle to debug Calico networking issues, please execute  `dcos node diagnostic create` to create a diagnostic bundle, and download the diagnostic bundle by executing `dcos node diagnostic download <diagnostic-bundle-name>`.
