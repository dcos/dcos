 #!/bin/bash

set -ex

cd /pkg/src/dcos-bootstrap-ca

# Enable go module support in Go 1.11
export GO111MODULE=on

# Install linter (needed for dcos-bootstrap-ca build
go get -u golang.org/x/lint/golint
make

mkdir -p $PKG_PATH/bin
install -m 755 /pkg/src/dcos-bootstrap-ca/bin/dcos-bootstrap-ca-linux $PKG_PATH/bin/dcos-bootstrap-ca
