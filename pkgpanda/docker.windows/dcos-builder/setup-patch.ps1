$ErrorActionPreference = "stop"

$url = 'https://github.com/mesos/3rdparty/raw/master/patch-2.5.9-7-setup.exe'
$file = 'c:\temp\patch-2.5.9-7-setup.exe'

Write-Output "Downloading $url"

Invoke-WebRequest -Uri $url -OutFile $file -MaximumRetryCount 5 -RetryIntervalSec 5

$INSTALL_ARGS = @("/VERYSILENT","/SUPPRESSMSGBOXES","/SP-")

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
