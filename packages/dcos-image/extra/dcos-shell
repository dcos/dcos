#!/bin/bash
set -o errexit -o nounset -o pipefail

source /opt/mesosphere/environment.export

if [ $# -eq 0 ]; then
  exec "$SHELL"
fi

exec "$@"
