#
# Simple helper script to do a full local  build

#set -x
Set-PSDebug -Trace 1

#set -o errexit -o pipefail

# Fail quickly if docker isn't working / up
docker ps

# Cleanup from previous build
#rm -rf /tmp/dcos_build_venv
Remove-Item -Recurse -Force c:/tmp/dcos_build_venv

# Force Python stdout/err to be unbuffered.
$env:PYTHONUNBUFFERED="notemtpy"

# Write a DC/OS Release tool configuration file which specifies where the build
# should be published to. This default config makes the release tool push the
# release to a folder in the current user's home directory.
$exists=Test-Path "dcos-release.config.yaml"
if ( ! $exists)
{
   $content =  "storage:`
  local:`
    kind: local_path`
    path: $HOME/dcos-artifacts`
options:`
  preferred: local`
  cloudformation_s3_url: https://s3-us-west-2.amazonaws.com/downloads.dcos.io/dcos"
   set-content "dcos-release.config.yaml" $content
}

# Create a python virtual environment to install the DC/OS tools to
python -m venv C:/tmp/dcos_build_venv
. "C:/tmp/dcos_build_venv/Scripts/activate.ps1"

# Install the DC/OS tools
./prep_local

# Build a release of DC/OS
$whom = ([Security.Principal.WindowsIdentity]::GetCurrent()).Name
release create $whom local_build
