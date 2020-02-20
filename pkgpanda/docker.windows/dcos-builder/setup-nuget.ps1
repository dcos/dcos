$ErrorActionPreference = "stop"

New-Item -Path "c:\" -Name "Bin" -ItemType "directory" -Force

$url = 'https://dist.nuget.org/win-x86-commandline/v4.1.0/nuget.exe'
$file = 'c:\Bin\nuget.exe'

Write-Output "Downloading $url"

Invoke-WebRequest -Uri $url -OutFile $file -MaximumRetryCount 5 -RetryIntervalSec 5
