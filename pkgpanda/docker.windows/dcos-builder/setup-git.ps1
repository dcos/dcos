$ErrorActionPreference = "stop"

$url = 'https://github.com/git-for-windows/git/releases/download/v2.16.1.windows.1/Git-2.16.1-64-bit.exe'
$file = 'c:\temp\Git-2.16.1-64-bit.exe'

Write-Output "Downloading $url"

Invoke-WebRequest -Uri $url -OutFile $file -MaximumRetryCount 5 -RetryIntervalSec 5

$INSTALL_ARGS = @("/SILENT")

$parameters = @{
    'FilePath' = $file
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
