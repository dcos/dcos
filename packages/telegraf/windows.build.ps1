$ErrorActionPreference = "stop"
New-Item -ItemType Directory "$env:PKG_PATH/bin"
New-Item -ItemType Directory "$env:PKG_PATH/conf"
new-item -Path "c:\gopath\src\github.com\influxdata" -type directory
copy-item -recurse  -Path C:\pkg\src\telegraf -Destination c:\gopath\src\github.com\influxdata\
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest https://github.com/golang/dep/releases/download/v0.5.0/dep-windows-amd64.exe -OutFile C:\gopath\src\github.com\influxdata\telegraf\dep.exe
Set-Location C:\gopath\src\github.com\influxdata\telegraf
$Env:DEPCACHEDIR="C:\tmp"
$Env:TEMP="C:\tmp"
$Env:TMP="C:\tmp"
.\dep.exe ensure -vendor-only -v
Set-Location C:\gopath\src\github.com\influxdata\telegraf\
$env:GOOS="windows"
$env:GOARCH="386"
go build .\cmd\telegraf\
Copy-Item -Path "telegraf.exe" -Destination "$env:PKG_PATH/bin/"
Copy-Item "c:\pkg\extra\telegraf.nssm.j2" "$env:PKG_PATH/conf/"
Copy-Item "c:\pkg\extra\telegraf.extra.j2" "$env:PKG_PATH/conf/"
