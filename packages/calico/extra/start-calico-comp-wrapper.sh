#!/usr/bin/env bash

set -xe

export NODENAME=`hostname`

exec "$@"
