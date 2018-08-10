$ErrorActionPreference = "Stop"

$MESOSPHERE_DIR = Join-Path $env:SystemDrive "opt\mesosphere"
$ZIP_PATH = Join-Path $env:SystemDrive "pkg\src\windows-apache\httpd-2.4.37-o102p-x64-vc14.zip"


. "$MESOSPHERE_DIR\environment.export.ps1"

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"

7z.exe x $ZIP_PATH "-o$env:PKG_PATH\bin\"
if($LASTEXITCODE -ne 0) {
    Throw "Failed to unzip Apache2 Windows package"
}
