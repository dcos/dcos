$ErrorActionPreference = "Stop"

$MESOSPHERE_DIR = Join-Path $env:SystemDrive "opt\mesosphere"
$DCOS_NET_DIR = Join-Path $env:SystemDrive "dcos-net"
$PKG_DIR = Join-Path $env:SystemDrive "pkg"


. "$MESOSPHERE_DIR\environment.export.ps1"

Copy-Item -Recurse -Path "$PKG_DIR\src\dcos-net" -Destination $DCOS_NET_DIR
Push-Location $DCOS_NET_DIR

$env:LDFLAGS = " /LIBPATH:$("$MESOSPHERE_DIR\bin" -replace '\\', '/') libsodium.lib "
$env:CFLAGS = " -I$("$MESOSPHERE_DIR\include" -replace '\\', '/') "
& "${env:ProgramFiles}\erlang\bin\escript.exe" "$DCOS_NET_DIR\rebar3" "as", "windows", "release"
if($LASTEXITCODE -ne 0) {
    Throw "Failed to build dcos-net"
}
Copy-Item -Recurse "$DCOS_NET_DIR\_build\windows\rel\dcos-net" "$env:PKG_PATH"

New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\dcos.target.wants"
# Generate Windows systemd files
Copy-Item "$PKG_DIR\extra\dcos-net.windows.service" "$env:PKG_PATH\dcos.target.wants\dcos-net.service"
Copy-Item "$PKG_DIR\extra\dcos-net-watchdog.windows.service" "$env:PKG_PATH\dcos.target.wants\dcos-net-watchdog.service"
Copy-Item "$PKG_DIR\extra\dcos-gen-resolvconf.windows.service" "$env:PKG_PATH\dcos.target.wants\dcos-gen-resolvconf.service"
Copy-Item "$PKG_DIR\extra\dcos-gen-resolvconf.windows.timer" "$env:PKG_PATH\dcos.target.wants\dcos-gen-resolvconf.timer"
# Copy necessary scripts
copy-item "$PKG_DIR\extra\dcos-net-setup.ps1" "$env:PKG_PATH\dcos-net\bin"
copy-item "$PKG_DIR\extra\dcos-net-watchdog.py" "$env:PKG_PATH\dcos-net\bin"
copy-item "$PKG_DIR\extra\gen_resolvconf.ps1" "$env:PKG_PATH\dcos-net\bin"
