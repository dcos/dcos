## Overview

This package provides DC/OS Calico component to support Calico networking containers and network policy in DC/OS.

<!-- MarkdownTOC -->

* [1. System Requirements](#1-system-requirements)
  - [1.1. Network Requirements](#11-network-requirements)
* [2. DC/OS Calico Components](#2-dcos-calico-components)
  - [2.1. DC/OS Calico Services](#21-dcos-calico-services)
* [3. DC/OS Configuration Reference \(Networking\)](#3-dcos-configuration-reference-networking)
* [4. Application Example](#4-application-example)
  - [4.1. Calico Networking \(Universal Container Runtime\)](#41-calico-networking-universal-container-runtime)
  - [4.2. Calico Networking \(Docker Engine\)](#42-calico-networking-docker-engine)
* [5. Administration Topics](#5-administration-topics)
  - [5.1. Network Policies](#51-network-policies)
  - [5.2. Default Profile](#52-default-profile)
  - [5.3. Network Policy Examples](#53-network-policy-examples)
    * [5.3.1. Launch Marathon Applications](#531-launch-marathon-applications)
    * [5.3.2. Frontends and Server Connectivity Test](#532-frontends-and-server-connectivity-test)
    * [5.3.3. Apply Network Policy](#533-apply-network-policy)
  - [5.4. Adding Network Profiles](#54-adding-network-profiles)
* [6. Migrate Applications from DC/OS Overlay to Calico](#6-migrate-applications-from-dcos-overlay-to-calico)
  - [6.1. Marathon application\(aka DC/OS Services\)](#61-marathon-applicationaka-dcos-services)
  - [6.2. DC/OS Services Built on Top of dcos-common](#62-dcos-services-built-on-top-of-dcos-common)
* [7. Troubleshooting](#7-troubleshooting)
* [8. Development](#8-development)

<!-- /MarkdownTOC -->

## 1. System Requirements

### 1.1. Network Requirements

| Port | DC/OS Component | systemd Unit             | Source       | Destination  | Description                                                                                                                         |
|------|-----------------|--------------------------|--------------|--------------|-------------------------------------------------------------------------------------------------------------------------------------|
| 179  | Calico          | dcos-calico-bird.service | agent/master | agent/master | calico BGP networking                                                                                                               |
| 2379 | etcd            | dcos-etcd.service        | agent/master | agent/master | etcd requires this port to be open between masters for leader election and peering connections when using standalone etcd (clustered). |
| 2380 | etcd            | dcos-etcd.service        | master       | master       | etcd requires this port to be open between masters for leader election and peering connections when using standalone etcd              |
| 64000 | Calico          | dcos-calico-felix.service | agent/master | agent/master | (Configurable) calico VXLAN networking can be configurable by calico_vxlan_port, by default, this shares the same value with dcos overlay vxlan port  |
| 62091 | Calico          | dcos-calico-felix.service | agent/master | agent/master | TCP port that the Prometheus metrics server should bind to                                                                   |

## 2. DC/OS Calico Components

DC/OS Calico component integrates the [Calico networking](https://www.projectcalico.org) into DC/OS, by providing the Calico CNI plugin for Mesos Universal Container Runtime and the Calico libnetwork plugin for Docker Engine. In addition, the calico control panel will provide the functionality of configuring the network policy for DC/OS workloads.

### 2.1. DC/OS Calico Services

DC/OS Calico integrates Calico into DC/OS for managing container networking and network security, three services are introduced:

* `dcos-calico-bird.service`: A BGP client that exchanges routing information between hosts for Calico. [(source)](https://github.com/projectcalico/bird)
* `dcos-calico-confd.service`: The confd templating engine monitors etcd datastores and generating and reloading bird configuration dynamically. [(source)](https://github.com/projectcalico/node)
* `dcos-calico-felix.service`: the control panel for Calico networking to program routes and ACL's for containers. [(source)](https://github.com/projectcalico/node)
* `dcos-calico-libntwork-plugin.service`: the network plugin for Docker that provides Calico networking to the Docker Engine. [(source)](https://github.com/projectcalico/libnetwork-plugin)

## 3. DC/OS Configuration Reference (Networking)

| Parameter | Description |
|-----------|-------------|
| calico_network_cidr | Subnet allocated for calico. When windows is not enabled, this field MUST be set by the operator as a mandatory configuration considering possible unrecoverable accidents when the subnet used by Calico conflicts with the ones for infrastructure etc. The subnet specified by `calico_network_cidr` MUST not overlap with those for VXLAN backends or virtual networks defined for [DC/OS virtual networks](https://github.com/mesosphere/dcos-docs-site/blob/staging/pages/mesosphere/dcos/1.14/installing/production/advanced-configuration/configuration-reference/index.md#dcos_overlay_enable). Default: 172.29.0.0/16 ] |
| calico_vxlan_enabled | Control, whether IP-in-IP or VXLAN mode is used for calico, by default VXLAN, is suggested to be used instead of VXLAN. `calico_vxlan_enabled` is supposed to set to 'true' for the environment that IP in IP is not supported, like Azure. [Default: 'true'] |
| calico_ipinip_mtu | The MTU to set on the Calico IPIP tunnel device. This configuration works when calico_vxlan_enabled is set to be false. Please refer to [this](https://docs.projectcalico.org/v3.8/networking/mtu) for a suitable MTU configuration. [Default: 1480] |
| calico_vxlan_port | The UDP port used for calico VXLAN. This configuration works when calico_vxlan_enabled is set to be true. [Default: 4789] |
| calico_vxlan_vni | The virtual network ID used for calico VXLAN. This configuration works when calico_vxlan_enabled is set to be true. [Default: 4096] |
| calico_vxlan_mtu | The MTU to set on the Calico VXLAN tunnel device. This configuration works when calico_vxlan_enabled is set to be true. Please refer to [this](https://docs.projectcalico.org/v3.8/networking/mtu) for a suitable MTU configuration [Default: 1450] |
| calico_veth_mtu | The MTU to set on the veth pair devices, e.g. both the container interface and host-end interface. Please refer to [this](https://docs.projectcalico.org/v3.8/networking/mtu) for a suitable MTU configuration [Default: 1500] |

## 4. Application Example

### 4.1. Calico Networking (Universal Container Runtime)

To use Calico networking containers, you only have to specify the network name as `calico`.

The following marathon app definition example will launch a container using the _Mesos UCR engine_ and plug it to the `calico` network:

```json
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

### 4.2. Calico Networking (Docker Engine)

Like with the previous example, the following marathon app definition will launch a container using the _Docker Engine_ and plug it to the `calico` network:

```json
{
  "id": "/calico-docker",
  "instances": 1,
  "container": {
    "type": "DOCKER",
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

## 5. Administration Topics

### 5.1. Network Policies

Network policy provides the ability to control network traffic by an ordered set of rules applied to the endpoints specified by a label selector, please refer [here](https://docs.projectcalico.org/v3.8/reference/resources/networkpolicy) for a detailed explanation of policy rule definitions and label selector syntax.

In DC/OS, Calico network policy is exposed directly to the operators, so that the operator can manage their traffic control according to different scenarios.

limitations on network policy we have in DC/OS:

* Calico network policy is a namespaced resource, but for now, we support only `default` namespace in DC/OS, and all the namespaced Calico resources should be defined under `default` namespace.
* Calico network policy takes effect only on Calico networking containers, which means labels set on non-Calico networking containers like `hostnetwork`, `dcos` and `bridge` will not count in Calico network policy.
* Labels work for network policy MUST be set in `NetworkInfo.Labels` in Mesos, and for Marathon, they should be in `networks.[].labels`, for example:

```js
{
  "id": "/client",
  "instances": 1,
   ...
  "networks": [
    {
      "mode": "container",
      "name": "calico",
      "labels": {
        "role": "client"
      }
    }
  ],
  ...
}
```

### 5.2. Default Profile

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

### 5.3. Network Policy Examples

In the following business isolation example, we have three application definitions as shown below, and both bookstore-frontend and bookstore-server are labeled with `"biz_type": "bookstore"`, while fruitstore-frontend is labeled with `"biz_type": "fruitstore"`. Here we will create a network policy to deny the requests from fruitstore-frontend to bookstore-server while allow requests from bookstore-frontend to bookstore-server.

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

#### 5.3.1. Launch Marathon Applications

The Marathon application definition of bookstore-frontend with policy label `"biz_type": "bookstore"`:

```json
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

```json
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

```json
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

#### 5.3.2. Frontends and Server Connectivity Test

Before applying network policy, the requests from bookstore-frontend and fruitstore-frontend to bookstore-server are successful, here we expect the FQDN `bookstore-server.marathon.containerip.dcos.thisdcos.directory` to return the bookstore-server container IP address:
```
$ dcos task exec fruitstore-frontend wget -qO- bookstore-server.marathon.containerip.dcos.thisdcos.directory:80/id
hubfeu2yculh%

$ dcos task exec bookstore-frontend wget -qO- bookstore-server.marathon.containerip.dcos.thisdcos.directory:80/id
hubfeu2yculh%
```

#### 5.3.3. Apply Network Policy

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

NOTE: Support for applying Calico network policy outside of the DC/OS cluster through DCOS CLI is comming soon, please refer to [DCOS-59091](https://jira.mesosphere.com/browse/DCOS-59091) for more details.

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

### 5.4. Adding Network Profiles

In most of the use cases a single calico profile is enough. However if for any reason more networks needs to be created, you should be aware of some corner cases.

> ⚠️ NOTE: The `calico-libnetwork-plugin` (the network interface to Docker Runtime) implicitly links the IP Pool to the calico profile associated with the respective calico docker network.

That said, to add a network profile, you should:

1. Create a new IP pool. For example:
  ```yaml
  apiVersion: v1
  kind: ipPool
  metadata:
    name: <pool-name>
    cidr: 10.1.0.0/16
  spec:
    nat-outgoing: true
    disabled: false
  ```
2. Create a new calico profile. For example:
  ```yaml
  apiVersion: projectcalico.org/v3
  kind: Profile
  metadata:
    name: <profile-name>
  spec:
    egress:
    + action: Allow
      destination: {}
      source: {}
    ingress:
    + action: Allow
      destination: {}
      source: {}
    labelsToApply:
      calico: ""
  ```
3. On **every agent**, create a new docker network that will use the new profile. You can use the following command, making sure the subnet matches the cidr from the pool:
  ```sh
  docker network create \
      --opt org.projectcalico.profile=<profile-name> \
      --driver calico \
      --ipam-driver calico-ipam \
      --subnet=10.1.0.0/16 \
      <network-name>
  ```

## 6. Migrate Applications from DC/OS Overlay to Calico

Automatic Migration for all services existing within a DC/OS cluster is impossible. Services can be launched by a variety of Apache Mesos frameworks ranging from production-proven platform [Marathon](https://mesosphere.github.io/marathon/) to services built on top of [dcos-common](https://github.com/mesosphere/dcos-commons. This includes existing, stateful services such as [Cassandra](https://docs.d2iq.com/mesosphere/dcos/services/cassandra) and [Spark](https://docs.d2iq.com/mesosphere/dcos/services/spark), or services being hosted from your environment.

### 6.1. Marathon application(aka DC/OS services)

There are at least two ways to effect a change for the Marathon application:

- DC/OS CLI
Update the application definition to replace the network name `dcos` with `calico`
`dcos app update calico_network_app.json`

for this method, the corresponding file, `calico_network_app.json` contains the definition of a Calico network application that differs from a DC/OS network application as follows:
```
   "networks": [
     {
       "mode": "container",
-      "name": "dcos"
+      "name": "calico"
     }
   ],
   "healthChecks": [],
```

- DC/OS GUI

Navigate to the networking tab for services, and change the network type from `Virtual Network: dcos` to `Virtual Network: calico`.

### 6.2. DC/OS services built on top of dcos-common

Normally, there are two components in DC/OS services:
- Scheduler - a Marathon application executing a plan to launch a Pod
- Pods - worker applications performing the service's responsibilities.

As the definition of the scheduler and pods are defined as release packages, and to make a permanent change in case the scheduler and Pods are using a virtual network, we have to generate new releases of DC/OS services after executing the following changes:

- For Schedulers
The Marathon application definition of a scheduler is defined as a template, marathon.json.mustache, inside the package definition, and is filled out by the operators according to the variables defined in `config.json`. The operator is expected to make sure `VIRTUAL_NETWORK_NAME` to be `calico` when the virtual network is enabled.

- For Pods
`dcos-common` allows pods to join virtual networks, with the `dcos` virtual network available by default. Migrating the application from `dcos` to `calico` requires the change as follows:

```
pods:
  pod-on-virtual-network:
    count: {{COUNT}}
    networks:
-     dcos:
+     calico:
    tasks:
      ...
  pod-on-host:
    count: {{COUNT}}
    tasks:
      ...
```

## 7. Troubleshooting

Diagnostic info including Calico resources, components logs, and BGP peer status are collected in DC/OS node diagnostic bundle to debug Calico networking issues, please execute  `dcos node diagnostic create` to create a diagnostic bundle, and download the diagnostic bundle by executing `dcos node diagnostic download <diagnostic-bundle-name>`.

## 8. Development

The address of calicoctl fork is [8], the libcalico-go fork is [9]. The CI job can be found in [1]. Each release of calicoctl should have a separate branch named release-vXXX-d2iq.YYY where XXX is the calico version (e.g. 3.12) and YYY is an internal build version (plain integer, e.g. `1`). The build from branch pushes into the dcos-calicoctl-artifacts bucket [2], sample URL for Linux binary is [3], darwin is [4], windows is [5]. Each build artifact from the release branch is auto removed after 7 days. The Jenkins task also builds from tags that are meant to be used in the dc/os CLI itself. The job build job for tags needs to be triggered manually (see [6] for reasoning). Once the tag build job finishes, the artifacts are pushed to download.mesosphere.io bucket into a path containing both parts of the commit sha and the sha of the binaries. Example URL for windows binary can be found in [7].

New releases can be done in the following way:

* pull the new release branch from the calicoctl upstream [10], e.g. release-v3.15
* push the branch into our calicoctl fork [8], use the name release-vXXX-d2iq.YYY, where XXX is the original version of the calicoctl (here it is 3.15) and YYY is the iteration number picked by us (e..g. `1`)
* check the revision of libcalico-go that new calicoctl release is using
* go to our fork of libcalico-go [9], create a new release branch (e.g. `release-v3.15.d2iq`) that matches the release that calicoctl is using, cherr-pick our changes (see the previous release branch's history to get the commit shas) on top of it.
* go back to our calicoctl fork [8], update the gomod reference replacement to match the libcalico-go version from the previous step. The command is. e.g. `go mod edit -replace=github.com/projectcalico/libcalico-go=github.com/vespian/libcalico-go@release-v3.12-d2iq`
* rebase all the other commits from the previous release, namelly the `Jenkinsfile` addition.
* push the new `release-v3.15-d2iq.1` branch into our fork [8]
* create new tag vXXX-d2iq.YYY tag (in our example it is going to be v3.15-d2iq.1), and push it to upstream repo [8]
* go to the calicoctl Jenkins job[1], and start the build job for tags manually.

As soon as the tasks finish, the artifacts will be available in `downloads.mesosphere.io`. Example URL can be seen in [7].

[1] https://jenkins.mesosphere.com/service/jenkins/view/DCOS%20Networking/job/calicoctl/<br/>
[2] https://s3.console.aws.amazon.com/s3/buckets/dcos-calicoctl-artifacts/autodelete7d/release-v3.12-d2iq/bin/?region=us-east-1&tab=overview<br/>
[3] https://dcos-calicoctl-artifacts.s3.amazonaws.com/autodelete7d/release-v3.12-d2iq/bin/calicoctl-linux-amd64<br/>
[4] https://dcos-calicoctl-artifacts.s3.amazonaws.com/autodelete7d/release-v3.12-d2iq/bin/calicoctl-darwin-amd64<br/>
[5] https://dcos-calicoctl-artifacts.s3.amazonaws.com/autodelete7d/release-v3.12-d2iq/bin/calicoctl-windows-amd64.exe<br/>
[6] https://stackoverflow.com/a/48276262<br/>
[7] https://s3.amazonaws.com/downloads.mesosphere.io/dcos-calicoctl/bin/v3.12.0-d2iq.1/fd5d699-b80546e/calicoctl-windows-amd64.exe<br/>
[8] https://github.com/dcos/calicoctl<br/>
[9] https://github.com/dcos/libcalico-go/<br/>
[10] https://github.com/projectcalico/calicoctl
