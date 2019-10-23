#!/usr/bin/env bash

set -xe

# the default configuration path, `/etc/calico/calicoctl.cfg`, of calicoctl is
# used to simply the interaction with Calico
/usr/bin/mkdir -p /etc/calico
/usr/bin/cp /opt/mesosphere/etc/calico/calicoctl.cfg /etc/calico/calicoctl.cfg

# failure to remove the calico-node docker container should not break starting
# calico node
/usr/bin/docker rm -f dcos-calico-node || true

/opt/mesosphere/bin/calicoctl apply -f \
	/opt/mesosphere/active/calico/etc/default_profile.yaml

dcos_node_private_ip=`/opt/mesosphere/bin/detect_ip`
/usr/bin/docker run --net=host --privileged \
 --name=dcos-calico-node \
 -e FELIX_IPINIPMTU=${CALICO_IPINIP_MTU} \
 -e FELIX_IGNORELOOSERPF=true \
 -e FELIX_VXLANPORT=${CALICO_VXLAN_PORT} \
 -e FELIX_VXLANMTU=${CALICO_VXLAN_MTU} \
 -e NODENAME=${CALICO_NODENAME} \
 -e IP=${dcos_node_private_ip} \
 -e IP6=${CALICO_IP6} \
 -e CALICO_NETWORKING_BACKEND=${CALICO_NETWORKING_BACKEND} \
 -e CALICO_IPV4POOL_IPIP=${CALICO_IPV4POOL_IPIP} \
 -e CALICO_IPV4POOL_VXLAN=${CALICO_IPV4POOL_VXLAN} \
 -e CALICO_IPV4POOL_NAT_OUTGOING=${CALICO_IPV4POOL_NAT_OUTGOING} \
 -e CALICO_IPV4POOL_CIDR=${CALICO_IPV4POOL_CIDR} \
 -e AS=${CALICO_AS} \
 -e NO_DEFAULT_POOLS=${CALICO_NO_DEFAULT_POOLS} \
 -e ETCD_ENDPOINTS=${ETCD_ENDPOINTS} \
 -v /var/log/calico:/var/log/calico \
 -v /var/lib/calico:/var/lib/calico \
 -v /run/docker/plugins:/run/docker/plugins \
 -v /lib/modules:/lib/modules \
 -v /var/run/calico:/var/run/calico \
 calico/node:${CALICO_NODE_VERSION}
