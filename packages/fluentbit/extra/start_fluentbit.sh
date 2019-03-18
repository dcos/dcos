#!/bin/bash

set -o errexit
set -o xtrace
set -o nounset

# Start fluentbit
exec /opt/mesosphere/bin/fluent-bit "$@"
