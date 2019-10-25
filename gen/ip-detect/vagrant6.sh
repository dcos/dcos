#!/usr/bin/env bash
set -o nounset -o errexit

get_defaultish_ip()
{
    ipv6=$(ip -6 route get 2001:4860:4860::8888 | awk '{print $9; exit}')
    echo $ipv6
}

echo $(get_defaultish_ip)
