$ErrorActionPreference = "stop"

$url = 'http://erlang.org/download/otp_win64_19.3.exe'
$file = 'c:\temp\otp_win64_19.3.exe'

Write-Output "Downloading $url"

Invoke-WebRequest -Uri $url -OutFile $file -MaximumRetryCount 5 -RetryIntervalSec 5

$INSTALL_DIR = Join-Path $env:ProgramFiles "erlang"
$INSTALL_ARGS = @( "/S", "/D=$INSTALL_DIR" )
 
$parameters = @{
    'FilePath' = $file
    'ArgumentList' = $INSTALL_ARGS
    'Wait' = $true
    'PassThru' = $true
}

Write-Output "Installing $file"

$p = Start-Process @parameters
if($p.ExitCode -ne 0) {
    Throw "Failed to install prerequisite $file during the environment setup"
}

Remove-Item -Path $file
