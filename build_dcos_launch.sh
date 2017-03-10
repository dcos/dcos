#!/bin/bash
#
# Simple helper script to build dcos-launch binary
# Note:
#  - must be run after this repo has been prepped with prep_local or prep_teamcity
#  - must be run after `mkpanda tree util` in order for package depedencies to be present
#  - must be maintained in sync with gen/build_deploy/bash.py
set -x -o errexit -o pipefail
# Force Python stdout/err to be unbuffered.
export PYTHONUNBUFFERED="notemtpy"
pushd packages/dcos-launch
# mkpanda will pump out the package path in the last line;
# this is required to grab only the binary built here
new_package_name=`mkpanda | tail -n 1 | cut -d':' -f2`
popd
mkdir -p tmp/dcos_build
cp $new_package_name tmp/dcos_build/dcos-launch.tar.xz
(cd tmp/dcos_build && tar -Jxf dcos-launch.tar.xz)
cp tmp/dcos_build/dcos-launch .
rm -rf tmp/dcos_build/
