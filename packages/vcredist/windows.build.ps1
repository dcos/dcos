# DO NOT MERGE
# This is a dummy change to trigger package version change in order to test
# winpanda upgrade feature. Read more here:
# - https://jira.d2iq.com/browse/D2IQ-66328
# - https://jira.d2iq.com/browse/D2IQ-65475

$ErrorActionPreference = "stop"
New-Item -ItemType Directory "$env:PKG_PATH/bin/install"
New-Item -ItemType Directory "$env:PKG_PATH/conf"
Copy-Item -Recurse -Path "c:/pkg/src/vcredist/*" "$env:PKG_PATH/bin/install"
Copy-Item "pkg/extra/vcredist.extra.j2" "$env:PKG_PATH/conf/"
Copy-Item "pkg/extra/vcredist.ps1" "$env:PKG_PATH/conf/"
Copy-Item "pkg/extra/vcredist_uninstall.ps1" "$env:PKG_PATH/conf/"
