$ErrorActionPreference = "stop"
copy-item -recurse  "c:\pkg\src\openstackservice" -destination "c:\"
push-location "c:\openstackservice"
nuget restore openstackservice.sln
msbuild openstackservice.sln /p:configuration=release
new-item -itemtype directory "$env:PKG_PATH\bin"
copy-item "release\openstackservice.exe" -destination "$env:PKG_PATH\bin"

