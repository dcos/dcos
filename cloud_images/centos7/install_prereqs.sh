#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

echo ">>> Kernel: $(uname -r)"
echo ">>> Updating system"
yum update --assumeyes

echo ">>> Disabling SELinux"
sed -i 's/SELINUX=enforcing/SELINUX=permissive/g' /etc/selinux/config

echo ">>> Adjusting SSH Daemon Configuration"

sed -i '/^\s*PermitRootLogin /d' /etc/ssh/sshd_config
echo -e "\nPermitRootLogin without-password" >> /etc/ssh/sshd_config

sed -i '/^\s*UseDNS /d' /etc/ssh/sshd_config
echo -e "\nUseDNS no" >> /etc/ssh/sshd_config

echo ">>> Disabling IPV6"
sysctl -w net.ipv6.conf.all.disable_ipv6=1
sysctl -w net.ipv6.conf.default.disable_ipv6=1

echo ">>> Installing DC/OS dependencies and essential packages"
yum install --assumeyes --tolerant lvm2 perl tar xz unzip curl bind-utils net-tools ipset libtool-ltdl rsync

echo ">>> Set up filesystem mounts systemd unit"
cat << 'EOF' > /etc/systemd/system/dcos_vol_setup.service
[Unit]
Description=Initial setup of volume mounts

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/dcos_vol_setup.sh /dev/xvde /var/lib/mesos
### ExecStart=/usr/local/sbin/dcos_vol_setup.sh /dev/xvdf /var/lib/docker
ExecStart=/usr/local/sbin/dcos_vol_setup.sh /dev/xvdg /dcos/volume0

[Install]
WantedBy=local-fs.target
EOF
systemctl enable dcos_vol_setup

echo ">>> Install Docker"
curl -fLsSv --retry 20 -Y 100000 -y 60 -o /tmp/docker-engine-1.11.2-1.el7.centos.x86_64.rpm \
  https://yum.dockerproject.org/repo/main/centos/7/Packages/docker-engine-1.11.2-1.el7.centos.x86_64.rpm
curl -fLsSv --retry 20 -Y 100000 -y 60 -o /tmp/docker-engine-selinux-1.11.2-1.el7.centos.noarch.rpm \
  https://yum.dockerproject.org/repo/main/centos/7/Packages/docker-engine-selinux-1.11.2-1.el7.centos.noarch.rpm
rpm -i /tmp/docker*.rpm || true
systemctl enable docker

echo ">>> Creating docker group"
/usr/sbin/groupadd -f docker

echo ">>> Customizing Docker storage driver to use devicemapper with thinpool"
docker_service_d=/etc/systemd/system/docker.service.d
mkdir -p "$docker_service_d"
cat << 'EOF' > "${docker_service_d}/execstart.conf"
[Service]
ExecStart=
ExecStart=/usr/bin/docker daemon -H fd:// --graph=/var/lib/docker --storage-driver=devicemapper --storage-opt=dm.thinpooldev=/dev/mapper/docker-thinpool --storage-opt dm.use_deferred_removal=true 
EOF

echo ">>> Adding group [nogroup]"
/usr/sbin/groupadd -f nogroup

echo ">>> Cleaning up SSH host keys"
shred -u /etc/ssh/*_key /etc/ssh/*_key.pub

echo ">>> Cleaning up accounting files"
rm -f rm -f /var/run/utmp
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

# Make sure we wait until all the data is written to disk, otherwise
# Packer might quite too early before the large files are deleted
sync
