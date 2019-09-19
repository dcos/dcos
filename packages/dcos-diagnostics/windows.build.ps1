$SRC_DIR = "c:\gopath\src\github.com\dcos\dcos-diagnostics\"
new-item -itemtype directory "c:\gopath\src\github.com\dcos"

copy-item -recurse  -Path c:/pkg/src/dcos-diagnostics/ -Destination c:/gopath/src/github.com/dcos/

Push-Location $SRC_DIR

VERSION := 0.4.0
COMMIT := $(shell git rev-parse --short HEAD)
LDFLAGS := -X github.com/dcos/dcos-diagnostics/config.Version=$(VERSION) -X github.com/dcos/dcos-diagnostics/config.Commit=$(COMMIT)

$env:GOOS = "windows"
& go build . -ldflags '$(LDFLAGS)'

new-item -itemtype directory "$env:PKG_PATH/bin"
Copy-Item -Path "$SRC_DIR/dcos-diagnostics.exe" -Destination "$env:PKG_PATH/bin/dcos-diagnostics.exe"

Pop-Location
