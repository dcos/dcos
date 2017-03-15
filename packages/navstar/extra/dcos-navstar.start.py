import errno
import subprocess
import os
# Startup script will try to execute all the commands. It will continue on error
# but will exit with an error if any failed.

retval = 0


# check that cmd executed and returned one of the values in `error_codes`
# prints error_msg if fails and sets retval to an error if a failure occurred
def check(cmd, error_msg='', error_codes=[0]):
    ...


# check that one of the cmds executed successfully
# prints error_msg if fails and sets retval to an error if a failure occurred
def oneof(cmds, error_msg='' ):
    ...


check('/bin/ping -c1 ready.spartan')
oneof(["/usr/bin/env modprobe ip_vs_wlc",
       "/usr/bin/env sh -c 'cat /lib/modules/$(uname -r)/modules.builtin | grep ip_vs_wlc'"],
       "Failed to load ip_vs_wlc kernel module or ip_vs_wlc is not builtin.")
check('/opt/mesosphere/bin/setup_iptables.sh')
check('/opt/mesosphere/bin/bootstrap dcos-navstar')
check('/opt/mesosphere/bin/bootstrap dcos-minuteman')
check('/usr/bin/mkdir -p /var/lib/dcos/navstar/mnesia')
check('/usr/bin/mkdir -p /var/lib/dcos/navstar/lashup')
check('/usr/bin/mkdir -p /var/lib/dcos/navstar/minuteman/dets')
oneof(["/usr/bin/env modprobe dummy",
       "/usr/bin/env sh -c 'cat /lib/modules/$(uname -r)/modules.builtin | grep dummy'"],
      "Failed to load dummy network interface kernel mdoule, or kernel module is not builtin." )
check('/usr/bin/env ip link add minuteman type dummy', error_codes=[0,errno.EEXIST])
check('/usr/bin/env ip link set minuteman up')

os.exit(retval)
