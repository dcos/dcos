#!/bin/sh
set -o nounset -o errexit

if [ -e /etc/environment ]
then
  set -o allexport
  source /etc/environment
  set +o allexport
fi

curl -fsSL http://169.254.169.254/latest/meta-data/public-ipv4
