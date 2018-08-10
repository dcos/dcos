$ErrorActionPreference = "Stop"

$MESOSPHERE_DIR = Join-Path $env:SystemDrive "opt\mesosphere"
$PKG_DIR = Join-Path $env:SystemDrive "pkg"


. "$MESOSPHERE_DIR\environment.export.ps1"

New-Item -ItemType "Directory" -Force -Path "$env:GOPATH\src\github.com\dcos"
Copy-item -Recurse -Force "$PKG_DIR\src\dcos-diagnostics" -Destination "$env:GOPATH\src\github.com\dcos"
Push-Location "$env:GOPATH\src\github.com\dcos\dcos-diagnostics"
$p = Start-Process -Wait -PassThru -FilePath "go.exe" -ArgumentList @("install")
if($p.ExitCode -ne 0) {
    Throw "Failed to build dcos-diagnostics"
}

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"
Copy-Item -Recurse -Force "$env:GOPATH\bin\*" "$env:PKG_PATH\bin"

$slaveServiceDir = Join-Path $env:PKG_PATH "dcos.target.wants_slave"
$slavePublicServiceDir = Join-Path $env:PKG_PATH "dcos.target.wants_slave_public"

New-Item -ItemType "Directory" -Force -Path $slaveServiceDir
New-Item -ItemType "Directory" -Force -Path $slavePublicServiceDir

Copy-Item -Path "$PKG_DIR\extra\dcos-diagnostics-agent.windows.service" -Destination "$slaveServiceDir\dcos-diagnostics.service"
Copy-Item -Path "$PKG_DIR\extra\dcos-diagnostics-agent.windows.service" -Destination "$slavePublicServiceDir\dcos-diagnostics.service"
