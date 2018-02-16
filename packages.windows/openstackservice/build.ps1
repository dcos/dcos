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
copy-item -recurse  "c:\pkg\src\openstackservice" -destination "c:\"
push-location "c:\openstackservice"
nuget restore openstackservice.sln
msbuild openstackservice.sln /p:configuration=release
new-item -itemtype directory "$pkgDest\bin"
copy-item "release\openstackservice.exe" -destination "$pkgDest\bin"

