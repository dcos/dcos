$ErrorActionPreference = "Stop"

$MESOSPHERE_DIR = Join-Path $env:SystemDrive "opt\mesosphere"
$PKG_DIR = Join-Path $env:SystemDrive "pkg"


. "$MESOSPHERE_DIR\environment.export.ps1"

New-Item -ItemType "Directory" -Force -Path "$env:GOPATH\src\github.com\dcos"
Copy-item -Recurse -Force "$PKG_DIR\src\dcos-metrics" -Destination "$env:GOPATH\src\github.com\dcos"
Push-Location "$env:GOPATH\src\github.com\dcos\dcos-metrics"
New-Item -ItemType "Directory" -Path ".\build"
$p = Start-Process -Wait -PassThru -FilePath "powershell.exe" -ArgumentList @(".\scripts\build.ps1", "collector", "statsd-emitter", "plugins")
if($p.ExitCode -ne 0) {
    Throw "Failed to build dcos-metrics"
}
New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"
Copy-Item -Path "$env:GOPATH\src\github.com\dcos\dcos-metrics\build\collector\dcos-metrics-collector-*" `
          -Destination "$env:PKG_PATH\bin\dcos-metrics.exe"
Copy-Item -Path "$env:GOPATH\src\github.com\dcos\dcos-metrics\build\statsd-emitter\dcos-metrics-statsd-emitter-*" `
          -Destination "$env:PKG_PATH\bin\statsd-emitter.exe"
Pop-Location

$agentServiceDir = Join-Path $env:PKG_PATH "dcos.target.wants_slave"
$agentPublicServiceDir = Join-Path $env:PKG_PATH "dcos.target.wants_slave_public"

New-Item -ItemType "Directory" -Force -Path $agentServiceDir
New-Item -ItemType "Directory" -Force -Path $agentPublicServiceDir

Copy-Item -Path "$PKG_DIR\extra\dcos-metrics-agent.windows.service" -Destination "$agentServiceDir\dcos-metrics-agent.service"
Copy-Item -Path "$PKG_DIR\extra\dcos-metrics-agent.windows.service" -Destination "$agentPublicServiceDir\dcos-metrics-agent.service"
