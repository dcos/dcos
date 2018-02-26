$FILENAME_PATH = "c:\temp\Git-2.16.1-64-bit.exe"
$INSTALL_ARGS = @("/SILENT")

$parameters = @{
    'FilePath' = $FILENAME_PATH
    'ArgumentList' = $INSTALL_ARGS
    'Wait' = $true
    'PassThru' = $true
}

Write-Output "Installing $FILENAME_PATH"

$p = Start-Process @parameters
if($p.ExitCode -ne 0) {
    Throw "Failed to install $FILENAME_PATH"
}

