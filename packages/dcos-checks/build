#!/bin/bash

set -e  # Fail the script if anything fails
set -x  # Verbose output
set -u  # Undefined variables

mkdir -p /pkg/src/github.com/dcos
mv /pkg/src/dcos-checks /pkg/src/github.com/dcos/
cd /pkg/src/github.com/dcos/dcos-checks

go install -v
cp -r /pkg/bin/ "$PKG_PATH"
