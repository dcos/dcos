$SRC_DIR = "c:\gopath\src\github.com\dcos\dcos-diagnistics\"
new-item -itemtype directory "c:\gopath\src\github.com\dcos"
copy-item -recurse  "c:\pkg\src\dcos-diagnostics" -destination "c:\gopath\src\github.com\dcos\"
Push-Location $SRC_DIR
& make install
new-item -itemtype directory "$env:PKG_PATH/bin"
Pop-Location
