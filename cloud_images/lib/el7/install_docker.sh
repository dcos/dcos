#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

echo ">>> In install_docker.sh:"

echo ">>> Installing Docker CE"
curl -fLsSv --retry 20 -Y 100000 -y 60 -o /tmp/docker-engine-17.05.0.ce-1.el7.centos.x86_64.rpm \
  https://yum.dockerproject.org/repo/main/centos/7/Packages/docker-engine-17.05.0.ce-1.el7.centos.x86_64.rpm
curl -fLsSv --retry 20 -Y 100000 -y 60 -o /tmp/docker-engine-selinux-17.05.0.ce-1.el7.centos.noarch.rpm \
  https://yum.dockerproject.org/repo/main/centos/7/Packages/docker-engine-selinux-17.05.0.ce-1.el7.centos.noarch.rpm

yum -t -y install /tmp/docker*.rpm || true
systemctl enable docker

echo ">>> Creating docker group"
/usr/sbin/groupadd -f docker

echo ">>> Customizing Docker storage driver to use Overlay"
docker_service_d=/etc/systemd/system/docker.service.d
mkdir -p "${docker_service_d}"
cat << 'EOF' > "${docker_service_d}/execstart.conf"
[Service]
Restart=always
StartLimitInterval=0
RestartSec=15
ExecStartPre=-/sbin/ip link del docker0
ExecStart=
ExecStart=/usr/bin/dockerd --graph=/var/lib/docker --storage-driver=overlay
EOF
