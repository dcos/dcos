$ErrorActionPreference = "Stop"

# Same structure as `/etc/mesosphere/roles` for now.
New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\etc_master\roles\master"
New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\etc_slave\roles\slave"
New-Item -ItemType "Directory" -Force -Path "$env:PKG_PATH\etc_slave_public\roles\slave_public"
