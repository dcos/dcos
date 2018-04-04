$FILENAME_PATH = "c:\temp\cmake-3.9.0-win64-x64.msi"
$INSTALL_ARGS = @("/quiet", "/i", $FILENAME_PATH)

$parameters = @{
    'FilePath' = "msiexec.exe"
    'ArgumentList' = $INSTALL_ARGS
    'Wait' = $true
    'PassThru' = $true
}
Write-Output "Installing $FILENAME_PATH"

$p = Start-Process @parameters
if($p.ExitCode -ne 0) {
    Throw "Failed to install $FILENAME_PATH"
}

