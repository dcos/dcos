#!/bin/bash
set -o errexit -o nounset -o pipefail

# AWS profile with appropriate credentials for Packer to create the AMI
export AWS_PROFILE=${AWS_PROFILE:-"development"}

# Base CentOS 7 AMI and region
export SOURCE_AMI=${SOURCE_AMI:-"ami-c5af54a5"}
export SOURCE_AMI_REGION=${SOURCE_AMI_REGION:-"us-west-2"}

# Comma separated string of AWS regions to copy the resulting DC/OS AMI to
export DEPLOY_REGIONS=${DEPLOY_REGIONS:-"us-west-2"}

# The version component of the dcos-nvidia-drivers/ bucket to use
# for fetching the nVidia drivers
export NVIDIA_VERSION=${NVIDIA_VERSION:-"367.35"}

# Useful options include -debug and -machine-readable
PACKER_BUILD_OPTIONS=${PACKER_BUILD_OPTIONS:-""}

packer build $PACKER_BUILD_OPTIONS packer.json
