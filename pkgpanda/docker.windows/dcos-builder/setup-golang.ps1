$ErrorActionPreference = "stop"

$url = 'https://golang.org/dl/go1.13.3.windows-amd64.zip'
$file = 'c:\temp\go1.13.3.windows-amd64.zip'

Write-Output "Downloading $url"

Invoke-WebRequest -Uri $url -OutFile $file -MaximumRetryCount 5 -RetryIntervalSec 5

$INSTALL_DIR = Join-Path $env:SystemDrive ""
 
Write-Output "Extracting $file"
Expand-Archive -Path $file -DestinationPath $INSTALL_DIR

Remove-Item -Path $file
