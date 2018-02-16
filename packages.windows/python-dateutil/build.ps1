# includes basic code from building

[CmdletBinding(DefaultParameterSetName="Standard")]
param(
    [string]
    [ValidateNotNullOrEmpty()]
    $pkgSrc,  # Location of the packages tree sources

    [string]
    [ValidateNotNullOrEmpty()]
    $pkgDest  # Location of the packages tree compiled binaries

)

Write-Host "Building python-datutil"

#!/bin/bash
#source /opt/mesosphere/environment.export
#$LIB_INSTALL_DIR="$PKG_PATH/lib/python3.6/site-packages"
#mkdir -p "$LIB_INSTALL_DIR"

#pip3 install --no-deps --no-index --target="$LIB_INSTALL_DIR" /pkg/src/$PKG_NAME/*.whl
