$SRC_DIR = "c:\gopath\src\github.com\dcos\dcos-diagnostics\"
new-item -itemtype directory "c:\gopath\src\github.com\dcos"

copy-item -recurse  -Path c:/pkg/src/dcos-diagnostics/ -Destination c:/gopath/src/github.com/dcos/

Push-Location $SRC_DIR

$env:VERSION = 0.4.0
$env:COMMIT = $(git rev-parse --short HEAD)
$env:LDFLAGS = -X github.com/dcos/dcos-diagnostics/config.Version=$(VERSION) -X github.com/dcos/dcos-diagnostics/config.Commit=$(COMMIT)

$env:GOOS = "windows"
& go build . -ldflags '$($env:LDFLAGS)'

new-item -itemtype directory "$env:PKG_PATH/bin"
Copy-Item -Path "$SRC_DIR/dcos-diagnostics.exe" -Destination "$env:PKG_PATH/bin/dcos-diagnostics.exe"

Pop-Location
