#!/bin/sh
set -o nounset -o errexit

REGION=$(curl -H Metadata:true "http://169.254.169.254/metadata/instance/compute/location?api-version=2017-07-01&format=text" 2>/dev/null)
FAULT_DOMAIN=$(curl -H Metadata:true "http://169.254.169.254/metadata/instance/compute/platformFaultDomain?api-version=2017-04-02&format=text" 2>/dev/null)

echo "{\"fault_domain\":{\"region\":{\"name\": \"$REGION\"},\"zone\":{\"name\": \"$FAULT_DOMAIN\"}}}"
