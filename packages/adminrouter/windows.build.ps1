$ErrorActionPreference = "stop"
New-Item -ItemType Directory "$env:PKG_PATH/etc/"
New-Item  -Path "$env:PKG_PATH/etc/adminrouter/"
New-Item -ItemType Directory "c:\tmp"

Add-Type -AssemblyName System.IO.Compression.FileSystem
function Unzip {
    param([string]$zipfile, [string]$outpath)
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zipfile, $outpath)
}
Unzip "c:\pkg\src\OpenResty\openresty-1.15.8.2-win64.zip" "c:/tmp/openresty"
Copy-Item -Recurse -Path "c:\tmp\openresty\openresty-1.15.8.2-win64\*" "$env:PKG_PATH\bin\dcos-adminrouter\"
Copy-Item -Recurse -Path "C:\pkg\build\extra\src\*" "$env:PKG_PATH\etc\dcos-adminrouter\conf"
New-Item -ItemType Directory "$env:PKG_PATH\etc\dcos-adminrouter\logs"