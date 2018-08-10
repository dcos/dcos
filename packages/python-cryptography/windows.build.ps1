$ErrorActionPreference = "Stop"

$MESOSPHERE_DIR = Join-Path $env:SystemDrive "opt\mesosphere"
$PYTHON_PREFIX = Join-Path $env:SystemDrive "Python"
$PKG_DIR = Join-Path $env:SystemDrive "pkg"


. "$MESOSPHERE_DIR\environment.export.ps1"

New-Item -ItemType "Directory" -Force -Path $PYTHON_PREFIX

$params = @("install", "--no-deps", "--no-index", "--prefix=$PYTHON_PREFIX", "$PKG_DIR\src\asn1crypto\asn1crypto-0.23.0-py2.py3-none-any.whl")
$p = Start-Process -Wait -PassThru -FilePath "pip.exe" -ArgumentList $params
if($p.ExitCode -ne 0) {
    Throw ("Failed to install asn1crypto Python library. Exit code: $($p.ExitCode)")
}

$params = @("install", "--no-deps", "--prefix=$PYTHON_PREFIX", "$PKG_DIR\src\cffi")
$p = Start-Process -Wait -PassThru -FilePath "pip.exe" -ArgumentList $params
if($p.ExitCode -ne 0) {
    Throw ("Failed to install cffi Python library. Exit code: $($p.ExitCode)")
}

$params = @("install", "--no-deps", "--no-index", "--prefix=$PYTHON_PREFIX", "$PKG_DIR\src\cryptography\cryptography-2.2.1-cp36-cp36m-win_amd64.whl")
$p = Start-Process -Wait -PassThru -FilePath "pip.exe" -ArgumentList $params
if($p.ExitCode -ne 0) {
    Throw ("Failed to install cryptography Python library. Exit code: $($p.ExitCode)")
}

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"
Copy-Item -Recurse -Path $PYTHON_PREFIX -Destination "$env:PKG_PATH\bin\"
