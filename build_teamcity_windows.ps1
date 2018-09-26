#!/usr/bin/pwsh

# Usage: build_teamcity_windows [tree_variant ...]
# tree_variant: Name of a tree variant to build. If no tree variants are passed,
#               the "default" and "installer" tree variants are built.

Set-PSDebug -trace 2
$ErrorActionPreference = "Stop"

function now() { Get-Date -Format O }
function _scope_msg() {
    # Here we want to turn off `Set-PSDebug -trace 2` that is present when running the script
    # before we Write-Host the message to teamcity, if we do not do this a "duplicate" echo will
    # be printed to stderr and teamcity will error trying to parse the message because
    # the format is invalid.
    Set-PSDebug -off
    Write-Host "##teamcity[block$1 timestamp='$(now)' name='$2']"
    # Turn `Set-PSDebug -trace 2` back on now that we're done sending the message to teamcity
    Set-PSDebug -trace 2
}
function _scope_opened() {
    _scope_msg "Opened" $1
}
function _scope_closed() {
    _scope_msg "Closed" $1
}
function RemoveItemSafely([string]$item){
    if ( Test-Path $item ) {
        Remove-Item -Recurse -Force $item
    }
}

# If no tree variants are specified, build the windows and installer variants.
If ($args.count -eq 0) { $tree_variants=("windows", "windows.installer") }
Else { $tree_variants = $args }

# Fail quickly if docker daemon is not up
docker ps
If ( $LASTEXITCODE -ne 0 ) {
    exit -1
}

_scope_opened "cleanup"
# cleanup from previous builds
# *active.json and *.bootstrap.tar.xz must be cleaned up, otherwise
# Teamcity starts picking up artifacts from previous builds.
#
# We manually clean rather than having TeamCity always clean so that
# builds are quicker.
RemoveItemSafely dcos-release.config.yaml
RemoveItemSafely artifacts/
RemoveItemSafely packages/*.active.json
RemoveItemSafely packages/bootstrap.latest
RemoveItemSafely packages/*.bootstrap.tar.xz
RemoveItemSafely CHANNEL_NAME
RemoveItemSafely build/env
RemoveItemSafely dcos_generate_config*.sh
RemoveItemSafely wheelhouse/
_scope_closed "cleanup"

_scope_opened "setup"

# Force Python stdout/err to be unbuffered to
# have immediate feedback in TeamCity build logs.
${env:PYTHONUNBUFFERED}="notemtpy"

# enable pkgpanda virtualenv *ALWAYS COPY* otherwise the TC cleanup will traverse and corrupt system python
python.exe -m venv --clear --copies build/env
. build/env/Scripts/Activate.ps1
If ( $LASTEXITCODE -ne 0 ) {
     exit -1
}

If (!$env:TEAMCITY_BRANCH) { Write-Host "TEAMCITY_BRANCH must be set (determines the tag and testing/ channel)" }

If ("$env:TEAMCITY_BRANCH" -eq "<default>") {
  Write-Host "ERROR: Building with a branch name of <default> is not supported"
  exit 1
}

$TAG="${env:TEAMCITY_BRANCH}"
$CHANNEL_NAME="testing/${TAG}"

Write-Host tag: "$TAG"
Write-Host channel: "$CHANNEL_NAME"

Set-PSDebug -off
Write-Host "##teamcity[setParameter name='env.CHANNEL_NAME' value='$CHANNEL_NAME']"
Write-Host "##teamcity[setParameter name='env.TAG' value='$TAG']"
Set-PSDebug -trace 2

cp config/dcos-release-windows.config.yaml dcos-release.config.yaml

$DIR=$PSScriptRoot

& "$DIR\prep_teamcity_windows.ps1"
If ( $LASTEXITCODE -ne 0 ) {
     exit -1
}
_scope_closed "setup"

release create $TAG $TAG $tree_variants

mkdir -p artifacts
cp -r wheelhouse artifacts/

RemoveItemSafely artifacts/dcos_generate_config.*
