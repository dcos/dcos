#!/bin/bash
set -o errexit -o nounset -o pipefail

# AWS profile with appropriate credentials for Packer to create the AMI
export AWS_PROFILE=${AWS_PROFILE:-"development"}

# Base CentOS 7 AMI and region
export SOURCE_AMI=${SOURCE_AMI:-"ami-bd48b3c0"}
export SOURCE_AMI_REGION=${SOURCE_AMI_REGION:-"us-east-1"}
# Version upgraded to in install_prereqs.sh
export DEPLOY_REGIONS=${DEPLOY_REGIONS:-"us-east-1"}

# Useful options include -debug and -machine-readable
PACKER_BUILD_OPTIONS=${PACKER_BUILD_OPTIONS:-""}

packer build $PACKER_BUILD_OPTIONS packer.json
