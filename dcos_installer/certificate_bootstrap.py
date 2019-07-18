import os
import pathlib
import shutil
import subprocess
import tempfile

from urllib.parse import urlparse

from dcos_installer.config import Config
from gen import Bunch

PACKAGE_NAME = 'dcoscertstrap'
BINARY_PATH = '/genconf/bin'
CA_PATH = '/genconf/ca'
INSTALLER_PATH = '/genconf/serve/dcos_install.sh'


def _extract_package(package_path):
    os.makedirs(BINARY_PATH, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(['tar', '-xJf', package_path, '-C', td])

        shutil.move(
            pathlib.Path(td) / 'bin' / PACKAGE_NAME,
            pathlib.Path(BINARY_PATH) / PACKAGE_NAME)


def _init_ca(alt_names):
    os.makedirs(CA_PATH, mode=0o0700, exist_ok=True)
    cmd_path = pathlib.Path(BINARY_PATH) / PACKAGE_NAME
    subprocess.run([
        str(cmd_path), '-d', CA_PATH, 'init-ca', '--sans', ','.join(alt_names)
    ])


def _read_certificate():
    with open(pathlib.Path(CA_PATH) / 'root-cert.pem') as fp:
        return fp.read()


# This seemed simpler than figuring out how to hook the dcos_install.sh template renderer
def _mangle_installer(certificate, path):
    script = """\
# Bootstrap CA certificate
read -d '' ca_data << EOF || true
{}
EOF
echo "$ca_data" > {}

# Run it all
main
"""
    needle = "# Run it all"
    with tempfile.TemporaryFile() as tmp_fp:
        with open(INSTALLER_PATH) as script_fp:
            for line in script_fp:
                if line.strip() == needle:
                    tmp_fp.write(script.format(certificate, path).encode())
                    tmp_fp.seek(0)
                    break
                else:
                    tmp_fp.write(line.encode())
        with open(INSTALLER_PATH, 'wb') as script_fp:
            for line in tmp_fp:
                script_fp.write(line)


def initialize_exhibitor_ca(config: Config, gen: Bunch):
    package_path = pathlib.Path(
        '/genconf/serve') / gen.cluster_packages[PACKAGE_NAME]['filename']
    ca_alternative_names = [
        '127.0.0.1', 'localhost',
        urlparse(gen.arguments['bootstrap_url']).hostname
    ]
    conf = config.config

    # Only perform action for enterprise clusters when not explicitly disabled
    if not (gen.arguments['dcos_variant'] == "enterprise"
            and conf.get('exhibitor_security_enabled', True)):
        return

    _extract_package(package_path)
    _init_ca(ca_alternative_names)
    _mangle_installer(_read_certificate(), '/tmp/.root-cert.pem')
