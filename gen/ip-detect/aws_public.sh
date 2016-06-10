#!/bin/sh
set -o nounset -o errexit

curl -fsSL http://169.254.169.254/latest/meta-data/public-ipv4
