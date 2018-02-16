# includes basic code from building

[CmdletBinding(DefaultParameterSetName="Standard")]
param(
    [string]
    [ValidateNotNullOrEmpty()]
    $pkgSrc,  # Location of the packages tree sources

    [string]
    [ValidateNotNullOrEmpty()]
    $pkgDest  # Location of the packages tree compiled binaries

)

copy-item "c:\pkg\src\Application-Request-Routing\requestRouter_amd64.msi" "$env:PKG_PATH"
copy-item "c:\pkg\src\URLRewrite\rewrite_amd64_en-US.msi" "$env:PKG_PATH"
copy-item "c:\pkg\build\extra\*" "$env:PKG_PATH"
