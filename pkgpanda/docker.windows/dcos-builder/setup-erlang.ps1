$ErrorActionPreference = "Stop"

$FILENAME_PATH = "c:\temp\otp_win64.exe"
$INSTALL_DIR = Join-Path $env:ProgramFiles "erlang"

$parameters = @{
    'FilePath' = $FILENAME_PATH
    'ArgumentList' = @( "/S", "/D=$INSTALL_DIR" )
    'Wait' = $true
    'PassThru' = $true
}
Write-Output "Installing $FILENAME_PATH"
$p = Start-Process @parameters
if($p.ExitCode -ne 0) {
    Throw "Failed to install prerequisite $FILENAME_PATH during the environment setup"
}
