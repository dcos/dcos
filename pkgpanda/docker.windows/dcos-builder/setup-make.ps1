$FILENAME_PATH = "c:\temp\make-3.81.exe"
$INSTALL_ARGS = @("/VERYSILENT","/SUPPRESSMSGBOXES","/SP-")

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

