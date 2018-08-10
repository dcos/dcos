#
# Simple helper script to get a localhost dcos-image development environment up
# and running with clone of pkgpanda.
#
# Expects that it is being run inside of a virtual environment.
#
$ErrorActionPreference = "Stop"

if (!$env:VIRTUAL_ENV) {
   Write-Output "ERROR: Must be run in a python virtual environment. env:VIRTUAL_ENV is not set"
   exit 1
}

# Install the latest version of pip
python -m pip install -U pip
if( $LASTEXITCODE -ne 0 ) {
    Write-Output "ERROR: Failed to upgrade pip"
    exit 1
}

# Install the packages in editable mode to the virtual environment.
pip install -e $PWD
if( $LASTEXITCODE -ne 0 ) {
    Write-Output "ERROR: Failed to install the packages into the virtual environment"
    exit 1
}
