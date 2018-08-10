#!/usr/bin/pwsh
#
# Simple helper script to do a full local  build
$ErrorActionPreference = "Stop"

# Fail quickly if docker isn't working / up
docker ps 2>&1 > $null
if ( $LASTEXITCODE -ne 0 ) {
    Write-Output "ERROR: Docker is not installed or not present in the PATH"
    exit -1
}

$tmpdir = $env:TMPDIR
if ( ! $tmpdir ) {
    $tmpdir = $env:TMP
}

# Cleanup from previous build
if( Test-Path "$tmpdir/dcos_build_venv" ) {
    Remove-Item -Recurse -Force "$tmpdir/dcos_build_venv"
}

# Force Python stdout/err to be unbuffered.
$env:PYTHONUNBUFFERED="notempty"

# Write a DC/OS Release tool configuration file which specifies where the build
# should be published to. This default config makes the release tool push the
# release to a folder in the current user's home directory.
if ( ! (Test-Path "dcos-release.config.yaml") ) {
$config_yaml = 
"storage: `
   local: `
    kind: local_path `
    path: c:/dcos-artifacts `
options: `
  preferred: local `
  cloudformation_s3_url: https://s3-us-west-2.amazonaws.com/downloads.dcos.io/dcos"

   $config_yaml | Set-Content -Path "dcos-release.config.yaml"
}

# Create a python virtual environment to install the DC/OS tools to
python -m venv "$tmpdir/dcos_build_venv"
if( $LASTEXITCODE -ne 0 ) {
    Write-Output "ERROR: Cannot create dcos_build_venv"
    exit 1
}
. "$tmpdir/dcos_build_venv/Scripts/Activate.ps1"
if( $LASTEXITCODE -ne 0 ) {
    Write-Output "ERROR: Cannot activate dcos_build_venv"
    exit 1
}

pip install botocore
if( $LASTEXITCODE -ne 0 ) {
    Write-Output "ERROR: Cannot install botocore via pip"
    exit 1
}

# Install the DC/OS tools
./prep_local_windows.ps1
if( $LASTEXITCODE -ne 0 ) {
    Write-Output "ERROR: Failed to run prep_local_windows.ps1"
    exit 1
}

# Build a release of DC/OS
release create $env:USERNAME local_build windows windows.installer
if ( $LASTEXITCODE -ne 0 ) {
    Write-Output "ERROR: Failed to create the DC/OS release"
    exit 1
}
