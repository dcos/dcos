#!/bin/bash
set -o errexit -o nounset -o pipefail

# AWS profile with appropriate credentials for Packer to create the AMI
export AWS_PROFILE=${AWS_PROFILE:-"development"}

# Base CentOS 7 AMI and region
export SOURCE_AMI=${SOURCE_AMI:-"ami-a9b24bd1"}
export SOURCE_AMI_REGION=${SOURCE_AMI_REGION:-"us-west-2"}
# Version upgraded to in install_prereqs.sh
export DEPLOY_REGIONS=${DEPLOY_REGIONS:-"us-west-2"}

# The version component of the dcos-nvidia-drivers/ bucket to use
# for fetching the nVidia drivers
export NVIDIA_VERSION=${NVIDIA_VERSION:-"384.130"}

# Useful options include -debug and -machine-readable
PACKER_BUILD_OPTIONS=${PACKER_BUILD_OPTIONS:-""}

packer build $PACKER_BUILD_OPTIONS packer.json
