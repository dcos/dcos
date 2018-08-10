$ErrorActionPreference = "Stop"

$FILENAME_PATH = "c:\temp\go1.9.3.windows-amd64.zip"
$INSTALL_DIR = $env:SystemDrive

Write-Output "Extracting $FILENAME_PATH"
Expand-Archive $FILENAME_PATH -DestinationPath $INSTALL_DIR
