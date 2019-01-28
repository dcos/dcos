#!/bin/bash

# Create versions dir and set permissions correctly
mkdir -p /opt/mesosphere/active/dcos-ui-update-service/versions
chmod 775 /opt/mesosphere/active/dcos-ui-update-service/versions
chown root:dcos_ui_update_service /opt/mesosphere/active/dcos-ui-update-service/versions

# Create dist folder for symlinks
mkdir -p /opt/mesosphere/active/dcos-ui-update-service/dist
chmod 775 /opt/mesosphere/active/dcos-ui-update-service/dist
chown root:dcos_ui_update_service /opt/mesosphere/active/dcos-ui-update-service/dist

if [ -f /opt/mesosphere/active/dcos-ui-update-service/dist/ui ]
then
    echo "ui-update-service UI-Dist symlink already exists"
else
    echo "ui-update-service UI-Dist symlink does not exist, creating it."
    ln -s /opt/mesosphere/active/dcos-ui/usr /opt/mesosphere/active/dcos-ui-update-service/dist/ui
fi
chown root:dcos_ui_update_service /opt/mesosphere/active/dcos-ui-update-service/dist/ui
