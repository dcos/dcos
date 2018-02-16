#!/usr/bin/pwsh
PSDebug -Trace OFF

set -o errexit -o pipefail

func now { date +"%Y-%m-%dT%H:%M:%S.000" | tr -d '\n' ;}
func _scope_msg {
    # Here we want to turn off `-x` that is present when running the bash script
    # before we echo the message to teamcity, if we do not do this a "duplicate" echo will
    # be printed to stderr and teamcity will error trying to parse the message because
    # the format is invalid.
    set +x
    echo "##teamcity[block$1 timestamp='$(now)' name='$2']"
    # Turn `-x` back on now that we're done sending the message to teamcity
    set -x
}
func _scope_opened {
    _scope_msg "Opened" $1
}
func _scope_closed {
    _scope_msg "Closed" $1
}

# Fail quickly if docker daemon is not up
systemctl status docker

_scope_opened "cleanup"
# cleanup from previous builds
# *active.json and *.bootstrap.tar.xz must be cleaned up, otherwise
# Teamcity starts picking up artifacts from previous builds.
#
# We manually clean rather than having TeamCity always clean so that
# builds are quicker.
rm -recurse -force dcos-release.config.yaml
rm -recurse -force artifacts/
rm -force packages/*.active.json
rm -force packages/bootstrap.latest
rm -force packages/*.bootstrap.tar.xz
rm -force CHANNEL_NAME
rm -recurse -force build/env
rm -force dcos_generate_config*.sh
rm -recurse -force wheelhouse/
_scope_closed "cleanup"

_scope_opened "setup"

# Force Python stdout/err to be unbuffered to
# have immediate feedback in TeamCity build logs.
$env:PYTHONUNBUFFERED="notemtpy"

# enable pkgpanda virtualenv *ALWAYS COPY* otherwise the TC cleanup will traverse and corrupt system python
python3.6 -m venv --clear --copies build/env
. build/env/bin/activate

: ${TEAMCITY_BRANCH?"TEAMCITY_BRANCH must be set (determines the tag and testing/ channel)"}

if ( "$TEAMCITY_BRANCH" == "<default>" ) {
  Write-Host "ERROR: Building with a branch name of <default> is not supported"
  exit 1
}

$TAG="$TEAMCITY_BRANCH"
$CHANNEL_NAME=testing/$TAG

Write-Host tag: "$TAG"
Write-Host channel: "$CHANNEL_NAME"

PSDebug -Trace 1
Write-Host "##teamcity[setParameter name='env.CHANNEL_NAME' value='$CHANNEL_NAME']"
Write-Host "##teamcity[setParameter name='env.TAG' value='$TAG']"
PSDebug -Trace OFF

cp config/dcos-release.config.yaml dcos-release.config.yaml

&$PSScriptRoot/prep_teamcity.ps1
_scope_closed "setup"

release create $TAG $TAG

mkdir -p artifacts
cp -r wheelhouse artifacts/

rm -recurse -force artifacts/dcos_generate_config.*
