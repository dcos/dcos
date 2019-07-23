#!/bin/bash

OS=$(uname -s | tr '[:upper:]' '[:lower:]')

# COPS-4642: using fork of terraform-aws-instance as spot instances are unsupported in dcos-terraform.
dcos_terraform_instance_aws="git::https://github.com/dcos/terraform-aws-spot-instance.git?ref=${DCOS_TERRAFORM_VERSION:-0.2.0}"

# Forked terraform:

# Terraformfile support to allow overriding module sources: https://github.com/hashicorp/terraform/pull/20229
URL_terraform="https://downloads.mesosphere.com/dcos-terraform/terraform/v0.11.13-mesosphere/${OS}_amd64/terraform"

# Forked terraform-provider-aws:

# Workaround IAM role creation race with spot instances: https://github.com/terraform-providers/terraform-provider-aws/pull/8556
# Retry InvalidTarget errors for AWS LB target group attachment: https://github.com/terraform-providers/terraform-provider-aws/pull/8538
# Make the ready timeout configurable for ELB and spot instance requests: https://github.com/terraform-providers/terraform-provider-aws/pull/8180
URL_terraform_provider_aws="https://downloads.mesosphere.com/dcos-terraform/terraform/v0.11.13-mesosphere/${OS}_amd64/terraform-provider-aws"

if [ "$OS" == "linux" ]; then
    CHECKSUM_terraform="19b19b9c979a75b523ce8ad044bade7a0987ce38f866cfe5479068531839f70c"
    CHECKSUM_terraform_provider_aws="245ba160a0389c2177091e2dbc72d79d034f1b0a93a5fee01d0d4b69f22be4e1"
elif [ "$OS" == "darwin" ]; then
    CHECKSUM_terraform="9bf9567bb0d396f83dd8ee2cedde5f188bdbba3316528648798e1d3f6814a1f7"
    CHECKSUM_terraform_provider_aws="bdb07595b393c2fba7e0a679e1d9355e9b30edeec138f48fd1ff9deb2065a8f9"
else
    # How did you even get here?
    echo "terraform_init.sh is not supported on Windows."
    exit 1
fi

# Check if a file matches an expected SHA256 checksum.
#   usage: checksum <filename> <sha256 hash>
function checksum {
    echo "$2  $1" |sha256sum --check /proc/self/fd/0 --quiet
}

# Download a binary over HTTPS if it does not exist or has an invalid checksum. The file will be marked executable
# after downloading.
# The download will be retried up to ten times if it fails.
#   usage: fetch <url> <sha256sum>
function fetch {
    filename=$(basename "$1")

    if ! checksum "$filename" "$2"; then
        for _ in $(seq 1 10); do
            wget "$1" -O "$filename" && break
            echo "$filename download failed. Retrying.."
            sleep 2
        done

        chmod +x "$filename"
        checksum "$filename" "$2"
    fi
}

if [ "$USE_SPOTBLOCK" != "0" ]; then
    cat << EOF > Terraformfile
{
 "dcos-terraform/instance/aws": {
   "source": "$dcos_terraform_instance_aws"
 }
}
EOF
else
    rm -f Terraformfile
fi

fetch "$URL_terraform" "$CHECKSUM_terraform"
fetch "$URL_terraform_provider_aws" "$CHECKSUM_terraform_provider_aws"

if [ ! -f ./id_rsa ]; then
    ssh-keygen -t rsa -f id_rsa
    cat id_rsa
fi

if [ -f main.tf ]; then
    for _ in $(seq 1 10); do
        ./terraform init && break
        echo "Terraform init failed Retrying.."
        sleep 2
    done
else
    echo -e "Download your main.tf file either from your build's artifacts or follow the DC/OS documentation to create one: https://docs.mesosphere.com/1.13/installing/evaluation/aws/#creating-a-dcos-cluster\n"
    echo -e "Once you have done that, run:\n\n  ./terraform init\n"
fi

if [ "$AWS_PROFILE" == "" ]; then
    echo -e "Login to AWS with maws:\n\n  eval \$(maws login \"account\")\n"
fi

if [ "$SSH_AUTH_SOCK" == "" ]; then
    echo -e "Load the SSH key into your SSH agent:\n\n  eval \$(ssh-agent)\n  ssh-add ./id_rsa\n"
else
    ssh-add ./id_rsa
fi

echo -e "Start the cluster:\n\n  ./terraform apply"
