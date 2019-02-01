#!/bin/bash

# Ensure env variables are loaded
set -a
source /opt/mesosphere/etc/dcos-ui-update-service.env
set +a

# Create versions dir and set permissions correctly
mkdir -p $DCOS_UI_UPDATE_VERSIONS_ROOT
chmod 775 $DCOS_UI_UPDATE_VERSIONS_ROOT

# Create dist folder for symlinks
mkdir -p $DCOS_UI_UPDATE_DIST_PATH
chmod 775 $DCOS_UI_UPDATE_DIST_PATH

chown -R root:dcos_ui_update_service $DCOS_UI_UPDATE_STATE_PATH

if [ -f $DCOS_UI_DIST_LINK ] 
then 
    echo "ui-update-service UI-Dist symlink already exists"
else
    echo "ui-update-service UI-Dist symlink does not exist, creating it."
    ln -s $DCOS_UI_UPDATE_DEFAULT_UI_PATH $DCOS_UI_UPDATE_DIST_LINK
fi
chown root:dcos_ui_update_service $DCOS_UI_UPDATE_DIST_LINK