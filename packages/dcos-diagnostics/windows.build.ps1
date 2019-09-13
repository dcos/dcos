$SRC_DIR = "c:\gopath\src\github.com\dcos\dcos-diagnostics\"
new-item -itemtype directory "c:\gopath\src\github.com\dcos"

copy-item -recurse  -Path c:/pkg/src/dcos-diagnostics/ -Destination c:/gopath/src/github.com/dcos/

Push-Location $SRC_DIR

& make install

new-item -itemtype directory "$env:PKG_PATH/bin"
Pop-Location
