$ErrorActionPreference = "Stop"

$MESOSPHERE_DIR = Join-Path $env:SystemDrive "opt\mesosphere"
$PYTHON_PREFIX = Join-Path $env:SystemDrive "Python"
$PKG_DIR = Join-Path $env:SystemDrive "pkg"


. "$MESOSPHERE_DIR\environment.export.ps1"

New-Item -ItemType "Directory" -Force -Path $PYTHON_PREFIX
$packages = @("Flask", "click", "flask-compress", "itsdangerous", "Werkzeug")
foreach($package in $packages) {
    $params = @("install", "--no-deps", "--prefix=$PYTHON_PREFIX", "$PKG_DIR\src\$package")
    $p = Start-Process -Wait -PassThru -FilePath "pip.exe" -ArgumentList $params
    if($p.ExitCode -ne 0) {
        Throw ("Failed to install $package Python library. Exit code: $($p.ExitCode)")
    }
}

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"
Copy-Item -Recurse -Path $PYTHON_PREFIX -Destination "$env:PKG_PATH\bin\"
