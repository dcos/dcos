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

$exclude = @('COPYRIGHT','README.txt','restydoc*')
Copy-Item -Recurse -Path "C:\Temp\openresty\openresty-1.15.8.2-win64\*" "$env:PKG_PATH\bin\" -Exclude $exclude

Copy-Item -Recurse -Path "C:\pkg\build\extra\src\errorpages" "$env:PKG_PATH\etc\"
Copy-Item -Recurse -Path "C:\pkg\build\extra\src\includes" "$env:PKG_PATH\conf\"
Copy-Item -Recurse -Path "C:\pkg\build\extra\src\lib" "$env:PKG_PATH\etc\"
Copy-Item "C:\pkg\build\extra\src\mime.types" "$env:PKG_PATH\conf\"
Copy-Item "C:\pkg\build\extra\src\nginx.agent.windows.conf" "$env:PKG_PATH\conf\"
Copy-Item "C:\pkg\build\adminrouter.nssm" "$env:PKG_PATH\conf\adminrouter.nssm.j2"
