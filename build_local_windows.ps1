#!/usr/bin/pwsh
#
# Simple helper script to do a full local  build

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
$config_yaml =
"storage: `
    azure: `
     kind: azure_block_blob `
     account_name: $env:AZURE_STORAGE_ACCOUNT `
     account_key: $env:AZURE_STORAGE_ACCESS_KEY `
     container: dcos `
     download_url: https://dcos.azureedge.net/dcos/dcos-windows/ `
    aws: `
        kind: aws_s3 `
        access_key_id: $env:AWS_ACCESS_KEY_ID `
        secret_access_key: $env:AWS_SECRET_ACCESS_KEY `
        bucket: downloads.dcos.io `
        object_prefix: dcos/dcos-windows `
        download_url: https://downloads.dcos.io/dcos/dcos-windows/
options: `
  preferred: aws `
  cloudformation_s3_url: https://s3-us-west-2.amazonaws.com/downloads.dcos.io/dcos/dcos-windows"

   $config_yaml | Set-Content -Path "dcos-release.config.yaml"

type dcos-release.config.yaml

# Create a python virtual environment to install the DC/OS tools to
python -m venv "$tmpdir/dcos_build_venv"
. "$tmpdir/dcos_build_venv/Scripts/Activate.ps1"

# Install the DC/OS tools
./prep_local_windows.ps1

# Build a release of DC/OS
release create $env:USERNAME local_build windows
