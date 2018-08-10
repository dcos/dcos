$ErrorActionPreference = "Stop"

$MESOSPHERE_DIR = Join-Path $env:SystemDrive "opt\mesosphere"
$PYTHON_DIR = Join-Path $env:SystemDrive "Python"
$PKG_DIR = Join-Path $env:SystemDrive "pkg"


. "$MESOSPHERE_DIR\environment.export.ps1"

Write-Output "Installing Python to directory: $PYTHON_DIR"
$parameters = @{
    'FilePath' = "$PKG_DIR\src\python\python-3.6.5-amd64.exe"
    'ArgumentList' = @("/quiet", "/passive", "InstallAllUsers=1", "PrependPath=1", "Include_test=0", "Include_pip=0", "Include_tcltk=0", "TargetDir=`"$PYTHON_DIR`"")
    'Wait' = $true
    'PassThru' = $true
}
$p = Start-Process @parameters
if ($p.ExitCode -ne 0) {
    Throw "Failed to install Python 3.6 amd64"
}

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"
Copy-Item -Recurse -Path $PYTHON_DIR -Destination "$env:PKG_PATH\bin\"
