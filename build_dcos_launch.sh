#!/bin/bash
#
# Simple helper script to build dcos-launch binary
# NOTE: this needs to be kept in sync with gen.build_deploy.bash::make_dcos_launch()

set -x
set -o errexit -o pipefail

# Cleanup from previous build
rm -rf /tmp/dcos_build_venv

# Force Python stdout/err to be unbuffered.
export PYTHONUNBUFFERED="notemtpy"

# Create a python virtual environment to install the DC/OS tools to
python3 -m venv /tmp/dcos_launch_venv
. /tmp/dcos_launch_venv/bin/activate

# Make a clean as possible clone
if [[ -n $(git -C $PWD status --porcelain -uno -z) ]]; then
  echo "Commit all changes before attempting to build!";
  exit 1;
fi
rm -rf /tmp/dcos-installer-build
git clone -q "file://$PWD" /tmp/dcos-installer-build/
pushd /tmp/dcos-installer-build
# Install the DC/OS tools
pip install -e /tmp/dcos-installer-build
cp gen/build_deploy/bash/dcos-launch.spec ./
pyinstaller --log-level=DEBUG dcos-launch.spec
popd
cp /tmp/dcos-installer-build/dist/dcos-launch ./
