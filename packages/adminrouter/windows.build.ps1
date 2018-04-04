$ErrorActionPreference = "stop"
copy-item "c:\pkg\src\Application-Request-Routing\requestRouter_amd64.msi" "$env:PKG_PATH"
copy-item "c:\pkg\src\URLRewrite\rewrite_amd64_en-US.msi" "$env:PKG_PATH"
copy-item "c:\pkg\build\extra\iis\web.config" "$env:PKG_PATH"
