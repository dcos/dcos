#!/bin/bash
#
# Simple helper script to do a full local  build

set -x
set -o errexit -o pipefail

# Fail quickly if docker isn't working / up
docker ps

# Cleanup from previous build
pyenv uninstall -f dcos

# Force Python stdout/err to be unbuffered.
export PYTHONUNBUFFERED="notemtpy"

# Write a DC/OS Release tool configuration file which specifies where the build
# should be published to. This default config makes the release tool push the
# release to a folder in the current user's home directory.
if [ ! -f dcos-release.config.yaml ]; then
cat <<EOF > dcos-release.config.yaml
storage:
  local:
    kind: local_path
    path: $HOME/dcos-artifacts
options:
  preferred: local
  cloudformation_s3_url: https://s3-us-west-2.amazonaws.com/downloads.dcos.io/dcos
EOF
fi

# Create a python virtual environment to install the DC/OS tools to
pyenv virtualenv 3.4.4 dcos

# Install the DC/OS tools
./prep_local

# Build a release of DC/OS
release create `whoami` local_build
