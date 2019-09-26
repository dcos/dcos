$FILENAME_PATH = "c:\temp\go1.12.9.windows-amd64.zip"
$INSTALL_DIR = Join-Path $env:SystemDrive ""
 
Write-Output "Extracting $FILENAME_PATH"
Expand-Archive $FILENAME_PATH -destinationpath $INSTALL_DIR

