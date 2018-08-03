#!/usr/bin/pwsh
#
# Simple helper script to do a full local  build

# Fail quickly if docker isn't working / up
Write-Output "docker ps"
docker ps
if ( $LASTEXITCODE -ne 0 ) {
    exit -1
}
Write-Output "setting tmpdir"
$tmpdir = $env:TMPDIR
if ( ! $tmpdir ) {
    Write-Output "TMPDIR was not set. setting to dollar sign env:TMP"
    $tmpdir = $env:TMP
}

# Cleanup from previous build
Write-Output "remove existing venv"

if (Test-Path "$tmpdir/dcos_build_env") {
    rm -Recurse "$tmpdir/dcos_build_venv"   
}

# Force Python stdout/err to be unbuffered.
Write-Output "set PYTHONUNBUFFERED to notempty"
$env:PYTHONUNBUFFERED="notempty"
Write-Output "set myhome"
$myhome = $HOME.replace("\", "/")

# Write a DC/OS Release tool configuration file which specifies where the build
# should be published to. This default config makes the release tool push the
# release to a folder in the current user's home directory.
Write-Output "set config_yaml"
if ( ! (Test-Path "dcos-release.config.yaml") ) {
$config_yaml = 
"storage: `
   local: `
    kind: local_path `
    path: $myhome/dcos-artifacts `
options: `
  preferred: local `
  cloudformation_s3_url: https://s3-us-west-2.amazonaws.com/downloads.dcos.io/dcos"

   $config_yaml | Set-Content -Path "dcos-release.config.yaml" 
}

# Create a python virtual environment to install the DC/OS tools to
Write-Output "create venv"
python -m venv "$tmpdir/dcos_build_venv"
Write-Output "activate venv"
. "$tmpdir/dcos_build_venv/Scripts/Activate.ps1"

# Install the DC/OS tools
Write-Output "run prep_local_windows.ps1"
./prep_local_windows.ps1

# Build a release of DC/OS
Write-Output "buidl the release"
release create $env:USERNAME local_build windows

