#!/bin/bash

# This script migrates an existing containers dir for an older DC/OS release
# to the new location for this release. This script exits early with success
# if the legacy containers dir doesn't exist, so it should only perform the
# migration after an upgrade.

set -o errexit
set -o nounset


USAGE="usage: $0 LEGACY_CONTAINERS_DIR TELEGRAF_CONTAINERS_DIR"

function dir_contains_files() {
    directory="$1"
    files=$(shopt -s nullglob dotglob; echo "${directory}"/*)
    if (( ${#files} )); then
        return 0
    fi
    return 1
}

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

if dir_contains_files "${TELEGRAF_CONTAINERS_DIR}"; then
    echo "ERROR: Can't migrate ${LEGACY_CONTAINERS_DIR} because destination ${TELEGRAF_CONTAINERS_DIR} contains files. Exiting." >&2
    exit 1
fi

# Delete destination dir if it exists, so we don't move the legacy dir *into* it.
if [ -d "${TELEGRAF_CONTAINERS_DIR}" ]; then
    rmdir "${TELEGRAF_CONTAINERS_DIR}"
fi

echo "Migrating ${LEGACY_CONTAINERS_DIR} to ${TELEGRAF_CONTAINERS_DIR}..."
mv "${LEGACY_CONTAINERS_DIR}" "${TELEGRAF_CONTAINERS_DIR}"
echo "Done."
