$FILENAME_PATH = "c:\temp\otp_win64_19.3.exe"
$INSTALL_DIR = Join-Path $env:ProgramFiles "erlang"
$INSTALL_ARGS = @( "/S", "/D=$INSTALL_DIR" )
 
$parameters = @{
    'FilePath' = $FILENAME_PATH
    'ArgumentList' = $INSTALL_ARGS
    'Wait' = $true
    'PassThru' = $true
}

Write-Output "Installing $FILENAME_PATH"

$p = Start-Process @parameters
if($p.ExitCode -ne 0) {
    Throw "Failed to install prerequisite $FILENAME_PATH during the environment setup"
}

