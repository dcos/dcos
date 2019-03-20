#!/bin/bash

set -o errexit
set -o xtrace
set -o nounset

# Start Fluent Bit
exec /opt/mesosphere/bin/fluent-bit "$@"
