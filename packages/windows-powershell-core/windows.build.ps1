$ErrorActionPreference = "Stop"

$MESOSPHERE_DIR = Join-Path $env:SystemDrive "opt\mesosphere"
$PKG_DIR = Join-Path $env:SystemDrive "pkg"


. "$MESOSPHERE_DIR\environment.export.ps1"

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin\PowerShell-Core"

7z.exe x "$PKG_DIR\src\windows-powershell-core\PowerShell-6.0.2-win-x64.zip" "-o$env:PKG_PATH\bin\PowerShell-Core"
if($LASTEXITCODE) {
    Throw "Failed to extract the PowerShell zip archive"
}
