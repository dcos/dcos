$ErrorActionPreference = "stop"

$url = 'https://aka.ms/vs/15/release/vs_buildtools.exe'
$file = 'c:\temp\vs_buildtools.exe'

Write-Output "Downloading $url"

Invoke-WebRequest -Uri $url -OutFile $file -MaximumRetryCount 5 -RetryIntervalSec 5

$INSTALL_ARGS = @('--quiet', '--wait', '--norestart', '--nocache',
    '--installPath', 'C:\BuildTools',
    '--add', 'Microsoft.VisualStudio.Workload.MSBuildTools',
    '--add', 'Microsoft.VisualStudio.Workload.VCTools',
    '--add', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
    '--add', 'Microsoft.VisualStudio.Component.VC.140',
    '--add', 'Microsoft.VisualStudio.Component.Windows10SDK.16299.Desktop',
    '--add', 'Microsoft.VisualStudio.Component.Windows81SDK',
    '--add', 'Microsoft.VisualStudio.Component.VC.ATL'
)

$parameters = @{
    'FilePath' = $file
    'ArgumentList' = $INSTALL_ARGS
    'Wait' = $true
    'PassThru' = $true
}
Write-Output "Installing $file"

$p = Start-Process @parameters
if($p.ExitCode -ne 0 -and $p.ExitCode -ne 2010) {
    Throw "Failed to install $file"
}

Remove-Item -Path $file
