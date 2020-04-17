$ErrorActionPreference = "stop"

$PKG_STORE = "$env:PKG_PATH\lib\bootstrap"

New-Item -ItemType Directory -Path $PKG_STORE -Force

Copy-Item -Recurse -Path "C:\pkg\build\extra\dcos_internal_utils" `
    "$PKG_STORE\dcos_internal_utils"

$packages = Get-ChildItem -Recurse -Path c:\pkg\src\  -Name -File
foreach ($package in $packages){
   & pip install "c:\pkg\src\$package" --target "$PKG_STORE"
}

New-Item -ItemType Directory -Path "$env:PKG_PATH\bin"

Copy-Item -Path "C:\pkg\build\extra\bin\bootstrap.ps1" `
    "$env:PKG_PATH\bin\bootstrap.ps1"
