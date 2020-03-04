$ErrorActionPreference = "stop"

$url = 'https://cmake.org/files/v3.9/cmake-3.9.0-win64-x64.msi'
$file = 'c:\temp\cmake-3.9.0-win64-x64.msi'

Write-Output "Downloading $url"

Invoke-WebRequest -Uri $url -OutFile $file -MaximumRetryCount 5 -RetryIntervalSec 5

$INSTALL_ARGS = @("/quiet", "/i", $file)

$parameters = @{
    'FilePath' = "msiexec.exe"
    'ArgumentList' = $INSTALL_ARGS
    'Wait' = $true
    'PassThru' = $true
}
Write-Output "Installing $file"

$p = Start-Process @parameters
if($p.ExitCode -ne 0) {
    Throw "Failed to install $file"
}

Remove-Item -Path $file
