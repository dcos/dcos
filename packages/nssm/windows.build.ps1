$ErrorActionPreference = "stop"
New-Item -ItemType Directory "$env:PKG_PATH/bin"
New-Item -ItemType Directory "$env:PKG_PATH/conf"
Add-Type -AssemblyName System.IO.Compression.FileSystem
function Unzip {
    param([string]$zipfile, [string]$outpath)
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zipfile, $outpath)
}
Unzip "c:\pkg\src\nssm\nssm-2.24-101-g897c7ad.zip" "c:\pkg\src\nssm\"

Copy-Item -Recurse -Path "c:/pkg/src/nssm/nssm-2.24-101-g897c7ad/win64/*" "$env:PKG_PATH/bin/"
Copy-Item "pkg/extra/nssm.extra.j2" "$env:PKG_PATH/conf/"
Copy-Item "pkg/extra/nssm.ps1" "$env:PKG_PATH/conf/"
