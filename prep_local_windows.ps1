#
# Simple helper script to get a localhost dcos-image development environment up
# and running with clone of pkgpanda.
#
# Expects that it is being run inside of a virtual environment.
#

if (!$env:VIRTUAL_ENV) {
   throw "Must be run in a python virtual environment"
}

# Install the latest version of pip
pip install -U pip

# Install the packages in editable mode to the virtual environment.
pip install -e $PWD
