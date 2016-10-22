#!/bin/bash
#
# Simple helper script to build dcos-spaceport binary for Linux
# NOTE: this needs to be kept in sync with gen.installer.bash::make_dcos_spaceport()

set -x
set -o errexit -o pipefail

# Cleanup from previous build
rm -rf /tmp/dcos_build_venv

# Force Python stdout/err to be unbuffered.
export PYTHONUNBUFFERED="notemtpy"

# Create a python virtual environment to install the DC/OS tools to
python3 -m venv /tmp/dcos_spaceport_venv
. /tmp/dcos_spaceport_venv/bin/activate

# Make a clean as possible clone
rm -rf /tmp/dcos-spaceport-build
git clone "file://$PWD" /tmp/dcos-spaceport-build
pushd /tmp/dcos-spaceport-build
# Install the DC/OS tools
pip install -e /tmp/dcos-spaceport-build
pyinstaller dcos-spaceport.spec
popd
cp /tmp/dcos-spaceport-build/dist/dcos-spaceport ./
