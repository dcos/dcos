$ErrorActionPreference = "Stop"

$MESOSPHERE_DIR = Join-Path $env:SystemDrive "opt\mesosphere"
$PKG_DIR = Join-Path $env:SystemDrive "pkg"


. "$MESOSPHERE_DIR\environment.export.ps1"

New-Item -ItemType "Directory" -Force -Path "$env:GOPATH\src\github.com\influxdata"
Copy-item -Recurse -Force "$PKG_DIR\src\telegraf" -Destination "$env:GOPATH\src\github.com\influxdata"

Push-Location "$env:GOPATH\src\github.com\influxdata\telegraf"
$p = Start-Process -Wait -PassThru -FilePath "go.exe" -ArgumentList @("get", "github.com/sparrc/gdm")
if($p.ExitCode -ne 0) {
    Throw "Failed to get gdm (Go dependency manager)"
}
$p = Start-Process -Wait -PassThru -FilePath "gdm.exe" -ArgumentList @("restore", "--parallel=false")
if($p.ExitCode -ne 0) {
    Throw "Failed to restore DC/OS telegraf dependencies via gdm"
}
$deps = @("github.com/StackExchange/wmi",
          "github.com/shirou/w32",
          "github.com/Microsoft/go-winio")
foreach($dep in $deps) {
    $p = Start-Process -Wait -PassThru -FilePath "go.exe" -ArgumentList @("get", $dep)
    if($p.ExitCode -ne 0) {
        Throw "Failed to get DC/OS telegraf dependency: $dep"
    }
}
$p = Start-Process -Wait -PassThru -FilePath "go.exe" -ArgumentList @("build", ".\cmd\telegraf")
if($p.ExitCode -ne 0) {
    Throw "Failed to build DC/OS telegraf"
}

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\bin"
Copy-Item -Path "$env:GOPATH\src\github.com\influxdata\telegraf\telegraf.exe" -Destination "$env:PKG_PATH\bin\"
Copy-Item -Path "$PKG_DIR\extra\dcos-telegraf-setup.ps1" -Destination "$env:PKG_PATH\bin\"

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\dcos.target.wants"
Copy-Item -Path "$PKG_DIR\extra\dcos-telegraf.windows.service" -Destination "$env:PKG_PATH\dcos.target.wants\dcos-telegraf.service"
