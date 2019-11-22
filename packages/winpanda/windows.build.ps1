$ErrorActionPreference = "stop"
Copy-Item -Recurse -Path "C:\pkg\build\extra\src\*" "$env:PKG_PATH"

$PKG_STORE = "$env:PKG_PATH\winpanda\lib\python36\site-packages"

New-Item -ItemType Directory -Path $PKG_STORE

$packages = Get-ChildItem -Recurse -Path c:\pkg\src\  -Name -File
foreach ($package in $packages){
   & pip install "c:\pkg\src\$package" --target $PKG_STORE
}


