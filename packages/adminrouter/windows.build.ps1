$ErrorActionPreference = "stop"
New-Item -ItemType Directory -Path "$env:PKG_PATH/etc/", "$env:PKG_PATH/etc/dcos-adminrouter/"
New-Item -ItemType Directory -Path "$env:PKG_PATH/etc/dcos-adminrouter/conf/", "$env:PKG_PATH/etc/dcos-adminrouter/logs/"
New-Item -ItemType Directory -Path "$env:PKG_PATH/bin/", "$env:PKG_PATH/bin/dcos-adminrouter/"
New-Item -ItemType Directory "c:\tmp"

Add-Type -AssemblyName System.IO.Compression.FileSystem
function Unzip {
    param([string]$zipfile, [string]$outpath)
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zipfile, $outpath)
}

Unzip "c:\pkg\src\OpenResty\openresty-1.15.8.2-win64.zip" "c:/tmp/openresty"

ls "C:\pkg\build\extra\src\"

Copy-Item -Recurse -Path "c:\tmp\openresty\openresty-1.15.8.2-win64\*" "$env:PKG_PATH\bin\dcos-adminrouter\"
Copy-Item -Recurse -Path "C:\pkg\build\extra\src\*" "$env:PKG_PATH\etc\dcos-adminrouter\conf\"
Copy-Item "$env:PKG_PATH\etc\dcos-adminrouter\conf\nginx.windows.agent.conf" "$env:PKG_PATH\etc\dcos-adminrouter\conf\nginx.conf"
