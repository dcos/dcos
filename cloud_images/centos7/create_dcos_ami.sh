#!/bin/bash
set -o errexit -o nounset -o pipefail

# AWS profile with appropriate credentials for Packer to create the AMI
export AWS_PROFILE=${AWS_PROFILE:-"development"}

# Base CentOS 7 AMI and region
export SOURCE_AMI=${SOURCE_AMI:-"ami-c5af54a5"}
export SOURCE_AMI_REGION=${SOURCE_AMI_REGION:-"us-west-2"}

# Comma separated string of AWS regions to copy the resulting DC/OS AMI to
export DEPLOY_REGIONS=${DEPLOY_REGIONS:-"ap-northeast-1,ap-southeast-1,ap-southeast-2,eu-central-1,eu-west-1,sa-east-1,us-east-1,us-west-1,us-west-2"}

packer build packer.json
