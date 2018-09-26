#!/usr/bin/pwsh
#
# Simple helper script to build wheels and install pkgpanda, dcos-image inside
# of CI
#
# Expects that it is being run inside of a virtual environment.

$ErrorActionPreference = "Stop"

if (!$env:VIRTUAL_ENV) {
    throw "Must be run in a python virtual environment"
}

# NOTE: If the directory already exists that is indeed a hard error. Should be
# cleaned up between builds to guarantee we get the artifacts we expect.
if ( Test-Path '.\wheelhouse' ) {
    Write-Host "wheelhouse folder must be deleted before prep_teamcity is rerun"
    exit 1
} Else {
   New-Item -Name "wheelhouse" -ItemType directory
}

# Make a clean copy of pkgpanda so the python artifacts build fast
$DIR="$PSScriptRoot"
$DcosImagePath="$DIR\ext\dcos-image"

Push-Location -Path $DIR
if ( Test-Path $DcosImagePath ) {
    cmd.exe /C "rmdir /S /Q $DcosImagePath"
}
git.exe clone "file://$DIR" $DcosImagePath
If ( $LASTEXITCODE -ne 0 ) {
     exit -1
}
 
$RevParse = $(git.exe rev-parse --verify "HEAD^{commit}")
If ( $LASTEXITCODE -ne 0 ) {
     exit -1
}

git.exe -C $DcosImagePath checkout -qf $RevParse
If ( $LASTEXITCODE -ne 0 ) {
     exit -1
}
Pop-Location

# Install the latest version of pip
python.exe -m pip install -U pip
If ( $LASTEXITCODE -ne 0 ) {
     exit -1
}

# We have wheel as a dependency since we use it to build the wheels
pip install wheel
If ( $LASTEXITCODE -ne 0 ) {
     exit -1
}

# Download distro independent artifacts
pip download -d wheelhouse $DcosImagePath
If ( $LASTEXITCODE -ne 0 ) {
     exit -1
}

# Make the wheels, they will be output into the folder `wheelhouse` by default.
pip wheel --wheel-dir=wheelhouse --no-index --find-links=wheelhouse $DcosImagePath
If ( $LASTEXITCODE -ne 0 ) {
     exit -1
}

# Install the wheels
pip install --no-index --find-links=wheelhouse dcos-image
If ( $LASTEXITCODE -ne 0 ) {
     exit -1
}

# Cleanup the checkout
cmd.exe /C "rmdir /S /Q $DcosImagePath"
