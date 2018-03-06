#!/usr/bin/pwsh
#
# Simple helper script to do a full local  build

Set-PSDebug -Trace 1

# Fail quickly if docker isn't working / up
docker ps
if ( $LASTEXITCODE -ne 0 ) {
    exit -1
}

$tmpdir = $env:TMPDIR
if ( ! $tmpdir ) {
    $tmpdir = $env:TMP
}

# Cleanup from previous build
rm -recurse "$tmpdir/dcos_build_venv"

# Force Python stdout/err to be unbuffered.
$env:PYTHONUNBUFFERED="notempty"

$myhome = $HOME.replace("\", "/")

# Write a DC/OS Release tool configuration file which specifies where the build
# should be published to. This default config makes the release tool push the
# release to a folder in the current user's home directory.
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
python -m venv "$tmpdir/dcos_build_venv"
. "$tmpdir/dcos_build_venv/Scripts/Activate.ps1"

# Install the DC/OS tools
./prep_local_windows.ps1

# Build a release of DC/OS
release create $env:USERNAME local_build --tree-variant windows

Set-PSDebug -Off
