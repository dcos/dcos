param (
    [Parameter(Mandatory=$true)] [string] $service
)

$ErrorActionPreference = "stop"

$PKG_STORE = "c:\d2iq\dcos\lib\bootstrap"

$Env:PYTHONPATH = "$PKG_STORE"

& python "c:\d2iq\dcos\bin\bootstrap" "$service"
