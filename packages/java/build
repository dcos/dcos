#!/bin/bash
set -o errexit -o nounset -o pipefail

mkdir -p "$PKG_PATH/usr"
cp -rp "/pkg/src/java" "$PKG_PATH/usr"

#edit JVM DNS caching timeout
echo "" >> $PKG_PATH/usr/java/jre/lib/security/java.security
echo "#Updated DNS cache ttl" >> $PKG_PATH/usr/java/jre/lib/security/java.security
echo "networkaddress.cache.ttl=10" >> $PKG_PATH/usr/java/jre/lib/security/java.security

mkdir -p "$PKG_PATH/bin"
ln -s "$PKG_PATH/usr/java/bin/java" "$PKG_PATH/bin/java"
ln -s "$PKG_PATH/usr/java/bin/java_vm" "$PKG_PATH/bin/java_vm"
ln -s "$PKG_PATH/usr/java/bin/jps" "$PKG_PATH/bin/jps"
ln -s "$PKG_PATH/usr/java/bin/keytool" "$PKG_PATH/bin/keytool"

# When updating Java, please change the following comment and check. If you need
# to downgrade from this version, please highlight the change on DC/OS channels.

# The OpenJDK 8 tarball hosted at https://downloads.mesosphere.com/java/
# was originally downloaded from
# https://github.com/AdoptOpenJDK/openjdk8-binaries/releases/download/

expected='openjdk version "1.8.0_265"'
version=$("$PKG_PATH/bin/java" -version 2>&1 | grep 'openjdk version')
if [ "$version" != "$expected" ]
then
	echo "Expected $expected, found $version" >&2
	exit 1
fi
