#!/bin/bash

# This script migrates an existing containers dir for an older DC/OS release
# to the new location for this release. This script exits early with success
# if the legacy containers dir doesn't exist, so it should only perform the
# migration after an upgrade.

set -o errexit
set -o nounset


USAGE="usage: $0 LEGACY_CONTAINERS_DIR TELEGRAF_CONTAINERS_DIR"

if [ "$#" -ne 2 ]; then
    echo "${USAGE}" >&2
    exit 1
fi

LEGACY_CONTAINERS_DIR="$1"
TELEGRAF_CONTAINERS_DIR="$2"

if [ ! -d "${LEGACY_CONTAINERS_DIR}" ]; then
    echo "Legacy containers dir ${LEGACY_CONTAINERS_DIR} does not exist. Skipping migration."
    exit 0
fi

echo "Migrating ${LEGACY_CONTAINERS_DIR} to ${TELEGRAF_CONTAINERS_DIR}..."
mv "${LEGACY_CONTAINERS_DIR}" "${TELEGRAF_CONTAINERS_DIR}"
echo "Done."
