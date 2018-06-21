#!/bin/bash
set -o errexit -o nounset -o pipefail

# AWS profile with appropriate credentials for Packer to create the AMI
export AWS_PROFILE=${AWS_PROFILE:-"development"}

# Base RHEL 7 AMI and region
export SOURCE_AMI=${SOURCE_AMI:-"ami-eba87093"}
export SOURCE_AMI_REGION=${SOURCE_AMI_REGION:-"us-west-2"}

# Comma separated string of AWS regions to copy the resulting DC/OS AMI to
export DEPLOY_REGIONS=${DEPLOY_REGIONS:-"us-west-2"}

# Useful options include -debug and -machine-readable
PACKER_BUILD_OPTIONS=${PACKER_BUILD_OPTIONS:-""}

packer build $PACKER_BUILD_OPTIONS packer.json
