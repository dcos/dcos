$ErrorActionPreference = "stop"
New-Item -ItemType Directory "$env:PKG_PATH/bin/install"
Copy-Item -Recurse -Path "c:/pkg/src/vcredist/*" "$env:PKG_PATH/bin/install"
