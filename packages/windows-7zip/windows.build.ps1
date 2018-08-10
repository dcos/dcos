$ErrorActionPreference = "Stop"

$INSTALLER_PATH = Join-Path $env:SystemDrive "pkg\src\windows-7zip\7z1801-x64.msi"
$7ZIP_DIR = Join-Path $env:SystemDrive "7-Zip"


New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"

cmd.exe /c start /wait msiexec /i $INSTALLER_PATH INSTALLDIR="$7ZIP_DIR" /qn
if($LASTEXITCODE -ne 0) {
    Throw ("Failed to install 7-Zip. Exit code: $LASTEXITCODE")
}

Copy-Item -Recurse -Path $7ZIP_DIR -Destination "$env:PKG_PATH\bin\"
