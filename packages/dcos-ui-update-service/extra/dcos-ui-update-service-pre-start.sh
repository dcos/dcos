#!/bin/bash

set -e  # Fail the script if anything fails
set -x  # Verbose output
set -u  # Undefined variables

echo "Loading env variables for dcos-ui-update-service pre-start script"
# Ensure env variables are loaded
set -a
source /opt/mesosphere/etc/dcos-ui-update-service.env
set +a

echo "Creating dcos-ui-update-service versions root: $DCOS_UI_UPDATE_VERSIONS_ROOT"
# Create versions dir and set permissions correctly
mkdir -p $DCOS_UI_UPDATE_VERSIONS_ROOT
chmod 775 $DCOS_UI_UPDATE_VERSIONS_ROOT

echo "Creating dcos-ui-update-service dist root: $DCOS_UI_UPDATE_DIST_PATH"
# Create dist folder for symlinks
mkdir -p $DCOS_UI_UPDATE_DIST_PATH
chmod 775 $DCOS_UI_UPDATE_DIST_PATH

echo "Ensure dcos_ui_update_service has ownership to dcos-ui-update-service's state path: $DCOS_UI_UPDATE_STATE_PATH"
chown -R root:dcos_ui_update_service $DCOS_UI_UPDATE_STATE_PATH

if [ -e $DCOS_UI_UPDATE_DIST_LINK ]
then
    echo "ui-update-service UI-Dist symlink already exists"
else
    echo "ui-update-service UI-Dist symlink does not exist, creating it."
    ln -s $DCOS_UI_UPDATE_DEFAULT_UI_PATH $DCOS_UI_UPDATE_DIST_LINK
fi
echo "Ensure dcos_ui_update_service has ownership of dcos-ui dist symlink: $DCOS_UI_UPDATE_DIST_LINK"
chown root:dcos_ui_update_service $DCOS_UI_UPDATE_DIST_LINK