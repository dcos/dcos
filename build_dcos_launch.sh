#!/bin/bash
#
# Simple helper script to build dcos-launch binary
# Note:
#  - must be run after this repo has been prepped with prep_local or prep_teamcity
#  - must be maintained in sync with gen/build_deploy/bash.py
set -x -o errexit -o pipefail
# Force Python stdout/err to be unbuffered.
export PYTHONUNBUFFERED="notemtpy"
pushd packages
# build all the pre-reqs to be safe
mkpanda tree --variant=util
pushd dcos-launch
# mkpanda will dump out the package path in the last line
# in the form <package_variant>:<package_path>.
# This is required to grab only the binary built here.
user_variant=$1
new_package_name=`mkpanda --variant ${user_variant:=default} | tail -n 1 | cut -d':' -f2`
popd
popd
mkdir -p tmp/dcos_build
cp $new_package_name tmp/dcos_build/dcos-launch.tar.xz
(cd tmp/dcos_build && tar -Jxf dcos-launch.tar.xz)
cp tmp/dcos_build/dcos-launch .
rm -rf tmp/dcos_build/
