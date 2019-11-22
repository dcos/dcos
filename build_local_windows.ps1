#!/usr/bin/pwsh
#
# Simple helper script to do a full local  build

$ErrorActionPreference = "Stop";

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
if ( Test-Path "$tmpdir/dcos_build_venv" ) {
    rm -recurse -force "$tmpdir/dcos_build_venv"
}

# Force Python stdout/err to be unbuffered.
$env:PYTHONUNBUFFERED="notempty"

$myhome = $HOME.replace("\", "/")

# Write a DC/OS Release tool configuration file which specifies where the build
# should be published to. This default config makes the release tool push the
# release to a folder in the current user's home directory.
$config_yaml =
"storage:
    azure:
     kind: azure_block_blob
     account_name: $env:AZURE_STORAGE_ACCOUNT
     account_key: $env:AZURE_STORAGE_ACCESS_KEY
     container: dcos
     download_url: https://dcos.azureedge.net/dcos/dcos-windows/
    aws:
        kind: aws_s3
        access_key_id: $env:AWS_ACCESS_KEY_ID
        secret_access_key: $env:AWS_SECRET_ACCESS_KEY
        bucket: downloads.dcos.io
        object_prefix: dcos/dcos-windows
        download_url: https://downloads.dcos.io/dcos/dcos-windows/
options:
  preferred: aws
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

# If release create returns non-zero exit code, then Fail, Deactivate and remove vEnv:
if ( $LASTEXITCODE -ne 0 ) {
    $release_lastexitcode = $LASTEXITCODE
    . "$tmpdir\dcos_build_venv\Scripts\deactivate.bat"
    rm -r -fo "$tmpdir/dcos_build_venv"
    Throw "The 'release create' command exited with error code: $release_lastexitcode"
}

# Remove previous dcos-release.config.yaml:
if ( Test-Path dcos-release.config.yaml ) {
    rm -fo dcos-release.config.yaml
}

# Creating temp dir, for instance:
$local_artifacts_dir = "./packages/cache"
mkdir -f $local_artifacts_dir

##Write DCOS installer locally
$config_yaml =
"storage:
   local:
    kind: local_path
    path: $local_artifacts_dir
options:
  preferred: local
  cloudformation_s3_url: https://s3-us-west-2.amazonaws.com/downloads.dcos.io/dcos"

   $config_yaml | Set-Content -Path "dcos-release.config.yaml"

type dcos-release.config.yaml
# Create a python virtual environment to install the DC/OS tools to
python -m venv "$tmpdir/dcos_build_venv"
. "$tmpdir/dcos_build_venv/Scripts/Activate.ps1"

# Install the DC/OS tools
./prep_local_windows.ps1
# Build a release of DC/OS
release create $env:USERNAME local_build windows

# If release create returns non-zero exit code, then Fail, Deactivate and remove vEnv:
if ( $LASTEXITCODE -ne 0 ) {
    $release_lastexitcode = $LASTEXITCODE
    . "$tmpdir\dcos_build_venv\Scripts\deactivate.bat"
    rm -r -fo "$tmpdir/dcos_build_venv"
    Throw "The 'release create' command exited with error code: $release_lastexitcode"
}

# Build tar ball for windows. 2 params: packages location and DC/OS variant:
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& .\build_genconf_windows.ps1 '$local_artifacts_dir\testing'"

# Import AWS modules on Azure TeamCity runner
Install-Module -Name AWS.Tools.Common -Force;
Install-Module -Name AWS.Tools.S3 -Force;

# Set and Read AWS Credentials:
Set-AWSCredential -AccessKey $env:AWS_ACCESS_KEY_ID -SecretKey $env:AWS_SECRET_ACCESS_KEY -StoreAs aws_s3_windows;
Set-AWSCredential -ProfileName aws_s3_windows;
Set-DefaultAWSRegion -Region us-west-2;

# Upload Tar Ball to dcos.download.io
Write-S3Object -BucketName "downloads.dcos.io" -Key "dcos\testing\$env:TEAMCITY_BRANCH\windows\dcos_generate_config_win.sh" -File ".\dcos_generate_config_win.sh" -CannedACLName public-read;
# Verify that the files were uploaded
Get-S3BucketWebsite -BucketName "downloads.dcos.io";
