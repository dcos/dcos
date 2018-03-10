$FILENAME_PATH = "c:\temp\go1.9.3.windows-amd64.zip"
$INSTALL_DIR = Join-Path $env:SystemDrive ""
 
Write-Output "Extracting $FILENAME_PATH"
Expand-Archive $FILENAME_PATH -destinationpath $INSTALL_DIR

