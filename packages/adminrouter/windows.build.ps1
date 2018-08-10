$ErrorActionPreference = "Stop"

$MESOSPHERE_DIR = Join-Path $env:SystemDrive "opt\mesosphere"
$PKG_DIR = Join-Path $env:SystemDrive "pkg"


. "$MESOSPHERE_DIR\environment.export.ps1"

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin\Apache24\conf"
Copy-Item "$PKG_DIR\extra\apache-windows\adminrouter.conf" "$env:PKG_PATH\bin\Apache24\conf"

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\dcos.target.wants"
Copy-Item "$PKG_DIR\extra\systemd\dcos-adminrouter-agent.windows.service" "$env:PKG_PATH\dcos.target.wants\dcos-adminrouter-agent.service"
