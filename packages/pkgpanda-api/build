#!/bin/bash

mkdir -p $PKG_PATH/etc/

cat <<EOF > $PKG_PATH/etc/pkgpanda-api.conf.py
WORK_DIR = '/run/dcos/pkgpanda-api/'
EOF

systemd_service=$PKG_PATH/dcos.target.wants/dcos-pkgpanda-api.service
mkdir -p $(dirname $systemd_service)
envsubst '${PKG_PATH}' < /pkg/extra/dcos-pkgpanda-api.service > "$systemd_service"

dst_file=$PKG_PATH/pkgpanda-api/bin/pkgpanda-api.sh
mkdir -p $(dirname $dst_file)
cp /pkg/extra/pkgpanda-api.sh $dst_file
chmod +x $dst_file
