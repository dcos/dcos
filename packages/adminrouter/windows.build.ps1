$ErrorActionPreference = "stop"
New-Item -ItemType Directory -Path "$env:PKG_PATH/conf/"
New-Item -ItemType Directory -Path "$env:PKG_PATH/etc/"
New-Item -ItemType Directory -Path "$env:PKG_PATH/bin/"


if (-not (Test-Path -LiteralPath "C:\Temp")) {
    New-Item -Path "C:\Temp" -ItemType Directory -ErrorAction Ignore | Out-Null #-Force
}
else {
    "Directory already existed"
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
function Unzip {
    param([string]$zipfile, [string]$outpath)
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zipfile, $outpath)
}

Unzip "c:\pkg\src\OpenResty\openresty-1.15.8.2-win64.zip" "c:/Temp/openresty"

Copy-Item -Recurse -Path "C:\Temp\openresty\openresty-1.15.8.2-win64\*" "$env:PKG_PATH\bin\"

Copy-Item -Recurse -Path "C:\pkg\build\extra\src\*" "$env:PKG_PATH\etc\"
Move-item -Path "$env:PKG_PATH\etc\includes" -Destination "$env:PKG_PATH\conf"
Move-item -Path "$env:PKG_PATH\etc\mime.types" -Destination "$env:PKG_PATH\conf"
Copy-Item "C:\pkg\build\dcos-adminrouter.nssm" "$env:PKG_PATH\conf\dcos-adminrouter.nssm.j2"
Copy-Item "$env:PKG_PATH\etc\nginx.agent.windows.conf" "$env:PKG_PATH\conf\nginx.conf"
