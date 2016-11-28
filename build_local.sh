#!/bin/bash
#
# Simple helper script to do a full local  build

set -x
set -o errexit -o pipefail

# Fail quickly if docker isn't working / up
docker ps

# Also fail quickly if Docker doesn't have enough memory to build some of the big components
DOCKER_MEMORY=$(docker info | grep Memory | awk '{print $3}')
if (( $(echo "$DOCKER_MEMORY < 5" | bc -l) )); then
    echo "Docker does not have enough memory for building the larger components. Exiting..."
    exit 1
fi

# Make sure we have gtar if we're on OS X
if [ "$(uname)" == "Darwin" ] && [ -z "$(which gtar)" ]; then
    echo "Please install GNU tar by running brew install gnu-tar"
    exit 1
fi

# Cleanup from previous build
rm -rf /tmp/dcos_build_venv

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
python3.5 -m venv /tmp/dcos_build_venv
. /tmp/dcos_build_venv/bin/activate

# Install the DC/OS tools
./prep_local

# Build a release of DC/OS
release create `whoami` local_build
