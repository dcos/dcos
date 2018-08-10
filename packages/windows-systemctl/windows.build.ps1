$ErrorActionPreference = "Stop"

$SYSTEMCTL_WIN_DIR = Join-Path $env:SystemDrive "pkg\src\systemctl-win\systemctl-win"


NuGet.exe restore "$SYSTEMCTL_WIN_DIR\systemctl-win.sln"
if ($LASTEXITCODE -ne 0) {
    Throw "nuget restore systemctl-win.sln failed in windows-systemctl build"
}

MSBuild.exe "$SYSTEMCTL_WIN_DIR\systemctl-win.sln" /p:configuration=release
if ($LASTEXITCODE -ne 0) {
    Throw "Failed to build windows-systemctl"
}

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"
Copy-Item -Path "$SYSTEMCTL_WIN_DIR\x64\release\systemctl.exe" -Destination "$env:PKG_PATH\bin\"
Copy-Item -Path "$SYSTEMCTL_WIN_DIR\x64\release\systemd-exec.exe" -Destination "$env:PKG_PATH\bin\"
