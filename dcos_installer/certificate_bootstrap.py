import logging
import os
import pathlib
import shutil
import subprocess
import tempfile

from typing import Any, Dict, List
from urllib.parse import urlparse

from dcos_installer.config import Config
from gen import Bunch

LOG = logging.getLogger(__name__)
PACKAGE_NAME = 'dcoscertstrap'
BINARY_PATH = '/genconf/bin'
CA_PATH = '/genconf/ca'
INSTALLER_PATH = '/genconf/serve/dcos_install.sh'


def _check(config: Dict[str, Any], variant: str) -> List[str]:
    """
    Current constraints are:
        config.yaml:
            exhibitor_tls_enabled == True,
            bootstrap_url must not be a local path
                This is necessary to prevent this orchestration
                from running when gen is not executed on a proper
                bootstrap node.
         DC/OS variant must be enterprise
    """
    checks = [
        (lambda: config.get('exhibitor_tls_enabled', True),
         'Exhibitor security is disabled'),
        (lambda: config['exhibitor_storage_backend'] == 'static',
         'Only static exhibitor backends are supported'),
        (lambda: variant == 'enterprise',
         'Exhibitor security is an enterprise feature'),
        (lambda: urlparse(config['bootstrap_url']).scheme != 'file',
         'Blackbox exhibitor security is only supported when using a remote'
         ' bootstrap node'),
    ]

    reasons = []
    for check in checks:
        if not check[0]():
            reasons.append(check[1])

    return reasons


def _extract_package(package_path: str):
    """ Extracts the dcoscertstrap package from the local pkgpanda
    repository """
    os.makedirs(BINARY_PATH, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(['tar', '-xJf', package_path, '-C', td])

        shutil.move(
            pathlib.Path(td) / 'bin' / PACKAGE_NAME,
            pathlib.Path(BINARY_PATH) / PACKAGE_NAME)


def _init_ca(alt_names: List[str]):
    """ Initializes the CA (generates a private key and self signed
    certificate CA extensions) """
    os.makedirs(CA_PATH, mode=0o0700, exist_ok=True)
    cmd_path = pathlib.Path(BINARY_PATH) / PACKAGE_NAME
    subprocess.run([
        str(cmd_path), '-d', CA_PATH, 'init-ca', '--sans', ','.join(alt_names)
    ])


def _read_certificate() -> str:
    with open(pathlib.Path(CA_PATH) / 'root-cert.pem') as fp:
        return fp.read()


def _mangle_installer(certificate: str, path: str):
    """ Modifies the installation script as a means of transferring the CA
     certificate to dcos nodes. This certificate is needed to validate the
     connection to the dcoscertstrap CSR service.
     """
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


def _get_ca_alt_name(config: Dict[str, Any]) -> str:
    """ Gets the bootstrap url hostname. Used to populate the CA SAN
    extension """
    return urlparse(
        config.get('exhibitor_bootstrap_ca_url',
                   config['bootstrap_url'])).hostname or ""


# noinspection PyUnresolvedReferences
def initialize_exhibitor_ca(config: Config, gen: Bunch):
    """ This is executed from backend.py after onprem_generate is called """
    conf = config.config

    reasons = _check(conf, gen.arguments['dcos_variant'])
    if reasons:
        LOG.info('Not bootstrapping exhibitor CA: %s', '\n'.join(reasons))
        return

    package_path = pathlib.Path(
        '/genconf/serve') / gen.cluster_packages[PACKAGE_NAME]['filename']
    ca_alternative_names = ['127.0.0.1', 'localhost', _get_ca_alt_name(conf)]

    _extract_package(package_path)
    _init_ca(ca_alternative_names)
    _mangle_installer(_read_certificate(), '/tmp/.root-cert.pem')
