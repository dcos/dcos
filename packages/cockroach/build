 #!/bin/bash

set -ex

cd /pkg/src/cockroach

# Copy the cockroach binary to the the package bin directory.
mkdir -p $PKG_PATH/bin
install -m 755 /pkg/src/cockroach/cockroach $PKG_PATH/bin/cockroach

# Copy the registration script to the package bin directory.
install -m 755 /pkg/extra/register.py $PKG_PATH/bin/register.py

# Copy the launch script to the package bin directory.
install -m 755 /pkg/extra/cockroach.sh $PKG_PATH/bin/cockroach.sh

# Copy the CockroachDB config updater program to the package bin directory.
install -m 755 /pkg/extra/cockroachdb-change-config.py $PKG_PATH/bin/cockroachdb-change-config.py

# Copy the IAM database backup/restore scripts to the package bin directory.
install -m 755 /pkg/extra/iam-database-backup.py $PKG_PATH/bin/iam-database-backup
install -m 755 /pkg/extra/iam-database-restore.py $PKG_PATH/bin/iam-database-restore

# Auto-start the dcos-cockroach service on the masters.
mkdir -p "$PKG_PATH/dcos.target.wants_master"
cp /pkg/extra/dcos-cockroach.service "$PKG_PATH/dcos.target.wants_master/dcos-cockroach.service"

# Auto-start the service for setting the CockroachDB config.
# (Important parts of the CockroachDB config cannot be set in the moment
# when starting a CockroachDB node, but must be set through TCP via
# CockroachDB's configuration update utility after running a node.)
cp /pkg/extra/dcos-cockroachdb-config-change.service "$PKG_PATH/dcos.target.wants_master/dcos-cockroachdb-config-change.service"
cp /pkg/extra/dcos-cockroachdb-config-change.timer "$PKG_PATH/dcos.target.wants_master/dcos-cockroachdb-config-change.timer"
