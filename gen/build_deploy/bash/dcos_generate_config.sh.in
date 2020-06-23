#!/bin/bash
# variant: {variant}
#
# All logging and tool output should be redirected to stderr
# as the Docker container might output json that would
# otherwise be tainted.
#
set -o errexit -o nounset -o pipefail

# preflight checks
docker version >/dev/null 2>&1 || {{ echo >&2 "docker should be installed and running. Aborting."; exit 1; }}

backout(){{
    if [ -f "{genconf_tar}" ]; then
        rm -f {genconf_tar}
    fi
    exit 1
}}
trap 'backout' INT

# if the tarball was previously extracted
if [ -f "{genconf_tar}" ]; then
    # but not successfully loaded into Docker
    if [ -z "$(docker images -q {docker_image_name} 2>/dev/null)" ]; then
        # remove the potentially corrupted tarball and
        # cause it to be re-extracted in the next step
        rm -f {genconf_tar}
    fi
fi

# extract payload and load into docker if not extracted
if [ ! -f "{genconf_tar}" ]; then
    >&2 echo Extracting image from this script and loading into docker daemon, this step can take a few minutes
    sed '1,/^#EOF#$/d' "$0" | tar xv
    >&2 docker load -i {genconf_tar}
fi
trap - INT

if [ ! -d genconf/state ]; then
    mkdir -p genconf/state
fi

DCOS_BOOTSTRAP_CA=dcos-bootstrap-ca

# kill any existing dcos-boostrap-ca processes before running genconf
kill $(pidof $DCOS_BOOTSTRAP_CA || true) 2>/dev/null || true

DCOS_INSTALLER_DAEMONIZE=${{DCOS_INSTALLER_DAEMONIZE:-false}}
DCOS_INSTALLER_CONTAINER_NAME=${{DCOS_INSTALLER_CONTAINER_NAME:-{genconf_tar}}}

if [ "$DCOS_INSTALLER_DAEMONIZE" == "true" ]; then
    docker run --name=$DCOS_INSTALLER_CONTAINER_NAME -d -v $(pwd)/genconf/:/genconf {docker_image_name} "$@"
else
    trap 'docker kill {genconf_tar}' HUP QUIT INT TERM
    docker run --rm --name=$DCOS_INSTALLER_CONTAINER_NAME -i -v $(pwd)/genconf/:/genconf {docker_image_name} "$@"
fi

if [ -d genconf/ca ]; then
    psk=$(cat genconf/ca/psk 2>/dev/null || echo "")
    if [ -z "$psk" ]; then
        echo "WARNING: DC/OS Bootstrap CA service PSK is unset"
    fi

    echo "Starting DC/OS Bootstrap CA service in the background"
    genconf/bin/$DCOS_BOOTSTRAP_CA -d genconf/ca/ serve --address :443 --psk "$psk" < /dev/null  &>/dev/null &
    echo
fi

exit 0
