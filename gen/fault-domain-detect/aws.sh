#!/bin/sh
set -o nounset -o errexit

# Get COREOS COREOS_PRIVATE_IPV4
if [ -e /etc/environment ]
then
  set -o allexport
  source /etc/environment
  set +o allexport
fi

echo '{"fault_domain":{"region":{"name": "aws-us-east-1"},"zone":{"name": "aws-us-east-1a"}}}'
