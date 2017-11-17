#!/opt/mesosphere/bin/python
import os
import shutil

# Normalize owner and file permissions of the Exhibitor TLS file artifacts
# (as opposed to simply erroring out upon detecting too wide file
# permissions).
truststore_path = '/var/lib/dcos/exhibitor-tls-artifacts/truststore.jks'
clientstore_path = '/var/lib/dcos/exhibitor-tls-artifacts/clientstore.jks'
serverstore_path = '/var/lib/dcos/exhibitor-tls-artifacts/serverstore.jks'

if os.path.exists(truststore_path) and \
   os.path.exists(clientstore_path) and \
   os.path.exists(serverstore_path):
    for file_path in [truststore_path, clientstore_path, serverstore_path]:
        shutil.chown(file_path, user='root', group='dcos_exhibitor')
        os.chmod(file_path, 0o640)
