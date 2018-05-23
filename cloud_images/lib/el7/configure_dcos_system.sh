#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

echo ">>> In configure_dcos_system.sh:"

echo ">>> Kernel: $(uname -r)"

echo ">>> Disabling SELinux"
sed -i 's/SELINUX=enforcing/SELINUX=permissive/g' /etc/selinux/config
setenforce permissive

echo ">>> Adjusting SSH Daemon Configuration"

sed -i '/^\s*PermitRootLogin /d' /etc/ssh/sshd_config
echo -e "\nPermitRootLogin without-password" >> /etc/ssh/sshd_config

sed -i '/^\s*UseDNS /d' /etc/ssh/sshd_config
echo -e "\nUseDNS no" >> /etc/ssh/sshd_config

echo ">>> Set up filesystem mounts"
mount_pairs=( "/dev/xvde:/var/lib/mesos"
              "/dev/nvme1n1:/var/lib/mesos"
              "/dev/xvdf:/var/lib/docker"
              "/dev/nvme2n1:/var/lib/docker"
              "/dev/xvdg:/dcos/volume0"
              "/dev/nvme3n1:/dcos/volume0"
              "/dev/xvdh:/var/log"
              "/dev/nvme4n1:/var/log"
            )
for mount_pair in ${mount_pairs[@]}; do
  device=$(echo ${mount_pair} | cut -d':' -f1)
  mountpoint=$(echo ${mount_pair} | cut -d':' -f2)
  device_filenamesafe=$(echo ${device} | sed 's/\//-/g')

  cat << EOF > /etc/systemd/system/dcos_vol_setup${device_filenamesafe}.service
  [Unit]
  Description=Initial setup of volume mounts
  DefaultDependencies=no
  Before=local-fs-pre.target

  [Service]
  Type=oneshot
  TimeoutSec=20
  ExecStart=/usr/local/sbin/dcos_vol_setup.sh ${device} ${mountpoint}

  [Install]
  WantedBy=local-fs-pre.target
EOF
  systemctl enable dcos_vol_setup${device_filenamesafe}
done

echo ">>> Disable rsyslog"
systemctl disable rsyslog

echo ">>> Set journald limits"
mkdir -p /etc/systemd/journald.conf.d/
echo -e "[Journal]\nSystemMaxUse=15G" > /etc/systemd/journald.conf.d/dcos-el7-ami.conf

echo ">>> Removing tty requirement for sudo"
sed -i'' -E 's/^(Defaults.*requiretty)/#\1/' /etc/sudoers

. /tmp/install_docker.sh

echo ">>> Adding group [nogroup]"
/usr/sbin/groupadd -f nogroup

echo ">>> Cleaning up SSH host keys"
shred -u /etc/ssh/*_key /etc/ssh/*_key.pub

echo ">>> Cleaning up accounting files"
rm -f /var/run/utmp
>/var/log/lastlog
>/var/log/wtmp
>/var/log/btmp

echo ">>> Remove temporary files"
rm -rf /tmp/* /var/tmp/*

echo ">>> Remove ssh client directories"
rm -rf /home/*/.ssh /root/.ssh

echo ">>> Remove history"
unset HISTFILE
rm -rf /home/*/.*history /root/.*history

echo ">>> Update /etc/hosts on boot"
update_hosts_script=/usr/local/sbin/dcos-update-etc-hosts
update_hosts_unit=/etc/systemd/system/dcos-update-etc-hosts.service

mkdir -p "$(dirname $update_hosts_script)"

cat << 'EOF' > "$update_hosts_script"
#!/bin/bash
export PATH=/opt/mesosphere/bin:/sbin:/bin:/usr/sbin:/usr/bin
curl="curl -s -f -m 30 --retry 3"
fqdn=$($curl http://169.254.169.254/latest/meta-data/local-hostname)
ip=$($curl http://169.254.169.254/latest/meta-data/local-ipv4)
echo "Adding $fqdn if $ip is not in /etc/hosts"
grep ^$ip /etc/hosts > /dev/null || echo -e "$ip\t$fqdn ${fqdn%%.*}" >> /etc/hosts
EOF

chmod +x "${update_hosts_script}"

cat << EOF > "${update_hosts_unit}"
[Unit]
Description=Update /etc/hosts with local FQDN if necessary
After=network.target

[Service]
Restart=no
Type=oneshot
ExecStart=${update_hosts_script}

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable $(basename "${update_hosts_unit}")


# Make sure we wait until all the data is written to disk, otherwise
# Packer might quit too early before the large files are deleted
sync
