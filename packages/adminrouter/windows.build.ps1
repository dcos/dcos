$ErrorActionPreference = "stop"
New-Item -ItemType Directory "$env:PKG_PATH/bin/Apache24/conf"
Copy-Item "pkg/extra/apache-windows/adminrouter.conf" "$env:PKG_PATH/bin/Apache24/conf"
