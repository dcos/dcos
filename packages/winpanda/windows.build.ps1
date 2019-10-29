$ErrorActionPreference = "stop"
New-Item -ItemType Directory -Path "$env:PKG_PATH/bin/", "$env:PKG_PATH/bin/winpanda/"

Copy-Item -Recurse -Path "C:\pkg\build\extra\src\*" "$env:PKG_PATH\bin/winpanda\"