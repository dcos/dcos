$ErrorActionPreference = "Stop"

$MESOSPHERE_DIR = Join-Path $env:SystemDrive "opt\mesosphere"
$PYTHON_PREFIX = Join-Path $env:SystemDrive "Python"
$PKG_DIR = Join-Path $env:SystemDrive "pkg"


. "$MESOSPHERE_DIR\environment.export.ps1"

New-Item -ItemType "Directory" -Force -Path $PYTHON_PREFIX

$whl = Get-Item "$PKG_DIR\src\$env:PKG_NAME\*.whl"
$params = @("install", "--no-deps", "--no-index", "--prefix=$PYTHON_PREFIX", "$whl")
$p = Start-Process -Wait -PassThru -FilePath "pip.exe" -ArgumentList $params
if($p.ExitCode -ne 0) {
    Throw ("Failed to install python-jinja2 library. Exit code: $($p.ExitCode)")
}

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"
Copy-Item -Recurse -Path $PYTHON_PREFIX -Destination "$env:PKG_PATH\bin\"
