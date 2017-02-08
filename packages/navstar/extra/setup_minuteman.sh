#!/bin/bash
# fail if any command fails
set -e
# only run if minuteman is enabled
if [[ ${ERL_FLAGS/-navstar enable_lb} != "$ERL_FLAGS" ]];then
  /usr/bin/env modprobe dummy
  # file exist is an acceptable error
  /usr/bin/env ip link add minuteman type dummy || [[ $? == 2 ]]
  /usr/bin/env ip link set minuteman up
  echo 0 > /proc/sys/net/bridge/bridge-nf-call-iptables
fi

