#!/bin/sh
set -o nounset -o errexit

get_private_ip_from_metaserver()
{
    curl -fsSL http://169.254.169.254/latest/meta-data/local-ipv4
}

get_private_ip_from_metaserver
