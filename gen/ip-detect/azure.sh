#!/usr/bin/env bash
set -o nounset -o errexit

get_defaultish_ip()
{
    local ipv4=$(ip route get 8.8.8.8 | awk '{ for(i=1; i<NF; i++) { if($i == "src") {print $(i+1); exit} } }')
    echo $ipv4
}

get_defaultish_ip
