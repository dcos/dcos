#
# Simple helper script to get a localhost dcos-image development environment up
# and running with clone of pkgpanda.
#
# Expects that it is being run inside of a virtual environment.
#
#set -o errexit -o nounset -o pipefail

if ( ! $env:VIRTUAL_ENV)
{
   Write-Output "Must be run in a python virtual environment"
   exit(-1)
}

# Install the latest version of pip
pip install -U pip

# Install the packages in editable mode to the virtual environment.
pip install -e $pwd
