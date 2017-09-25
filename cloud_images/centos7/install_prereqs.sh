#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

echo ">>> Kernel: $(uname -r)"
echo ">>> Updating system to $CENTOS_VERSION"
sed -i -e 's/^mirrorlist=/#mirrorlist=/' -e 's/^#baseurl=/baseurl=/' /etc/yum.repos.d/CentOS-Base.repo
yum -y --releasever=$CENTOS_VERSION update
sed -i -e 's/^#mirrorlist=/mirrorlist=/' -e 's/^baseurl=/#baseurl=/' /etc/yum.repos.d/CentOS-Base.repo

echo ">>> Disabling SELinux"
sed -i 's/SELINUX=enforcing/SELINUX=permissive/g' /etc/selinux/config
setenforce permissive

echo ">>> Adjusting SSH Daemon Configuration"

sed -i '/^\s*PermitRootLogin /d' /etc/ssh/sshd_config
echo -e "\nPermitRootLogin without-password" >> /etc/ssh/sshd_config

sed -i '/^\s*UseDNS /d' /etc/ssh/sshd_config
echo -e "\nUseDNS no" >> /etc/ssh/sshd_config

echo ">>> Installing DC/OS dependencies and essential packages"
yum -y --tolerant install perl tar xz unzip curl bind-utils net-tools ipset libtool-ltdl rsync nfs-utils

echo ">>> Set up filesystem mounts"
cat << 'EOF' > /etc/systemd/system/dcos_vol_setup.service
[Unit]
Description=Initial setup of volume mounts

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/dcos_vol_setup.sh /dev/xvde /var/lib/mesos
ExecStart=/usr/local/sbin/dcos_vol_setup.sh /dev/xvdf /var/lib/docker
ExecStart=/usr/local/sbin/dcos_vol_setup.sh /dev/xvdg /dcos/volume0
ExecStart=/usr/local/sbin/dcos_vol_setup.sh /dev/xvdh /var/log

[Install]
WantedBy=local-fs.target
EOF
systemctl enable dcos_vol_setup

echo ">>> Disable rsyslog"
systemctl disable rsyslog

echo ">>> Set journald limits"
mkdir -p /etc/systemd/journald.conf.d/
echo -e "[Journal]\nSystemMaxUse=15G" > /etc/systemd/journald.conf.d/dcos-el7-ami.conf

echo ">>> Removing tty requirement for sudo"
sed -i'' -E 's/^(Defaults.*requiretty)/#\1/' /etc/sudoers

echo ">>> Install Docker"
curl -fLsSv --retry 20 -Y 100000 -y 60 -o /tmp/docker-engine-1.13.1-1.el7.centos.x86_64.rpm \
  https://yum.dockerproject.org/repo/main/centos/7/Packages/docker-engine-1.13.1-1.el7.centos.x86_64.rpm
curl -fLsSv --retry 20 -Y 100000 -y 60 -o /tmp/docker-engine-selinux-1.13.1-1.el7.centos.noarch.rpm \
  https://yum.dockerproject.org/repo/main/centos/7/Packages/docker-engine-selinux-1.13.1-1.el7.centos.noarch.rpm
yum -y localinstall /tmp/docker*.rpm || true
systemctl enable docker

echo ">>> Creating docker group"
/usr/sbin/groupadd -f docker

echo ">>> Customizing Docker storage driver to use Overlay"
docker_service_d=/etc/systemd/system/docker.service.d
mkdir -p "$docker_service_d"
cat << 'EOF' > "${docker_service_d}/execstart.conf"
[Service]
Restart=always
StartLimitInterval=0
RestartSec=15
ExecStartPre=-/sbin/ip link del docker0
ExecStart=
ExecStart=/usr/bin/dockerd --graph=/var/lib/docker --storage-driver=overlay
EOF

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
yum clean all
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

chmod +x "$update_hosts_script"

cat << EOF > "$update_hosts_unit"
[Unit]
Description=Update /etc/hosts with local FQDN if necessary
After=network.target

[Service]
Restart=no
Type=oneshot
ExecStart=$update_hosts_script

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable $(basename "$update_hosts_unit")


# Make sure we wait until all the data is written to disk, otherwise
# Packer might quite too early before the large files are deleted
sync
