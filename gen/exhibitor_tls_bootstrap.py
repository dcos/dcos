import json
import os
import pathlib
import tempfile
import shutil
import subprocess

from typing import Any, Dict, List
from urllib.parse import urlparse

PACKAGE_NAME = 'dcoscertstrap'
BINARY_PATH = '/genconf/bin'
CA_PATH = '/genconf/ca'


def _check(config: Dict[str, Any]) -> List[str]:
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
        (lambda: config['exhibitor_tls_enabled'] == 'true',
         'Exhibitor security is disabled'),
        (lambda: config['exhibitor_storage_backend'] == 'static',
         'Only static exhibitor backends are supported'),
        (lambda: config['dcos_variant'] == 'enterprise',
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


def find_package(packages_json: str) -> str:
    packages = json.loads(packages_json)
    for package in packages:
        if package.startswith(PACKAGE_NAME):
            return package
    raise Exception('dcoscertstrap package is not present')


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
    certificate CA extensions) if the resulting files do not already exist """
    if not all(map(os.path.exists, [
            pathlib.Path(CA_PATH) / 'root-cert.pem',
            pathlib.Path(CA_PATH) / 'root-key.pem'])):
        os.makedirs(CA_PATH, mode=0o0700, exist_ok=True)
        cmd_path = pathlib.Path(BINARY_PATH) / PACKAGE_NAME
        subprocess.run([
            str(cmd_path), '-d', CA_PATH, 'init-ca', '--sans', ','.join(alt_names)
        ])
    else:
        print('[{}] CA files already exist'.format(__name__))


def _read_certificate() -> str:
    with open(pathlib.Path(CA_PATH) / 'root-cert.pem') as fp:
        return fp.read()


def _get_ca_alt_name(config: Dict[str, Any]) -> str:
    """ Gets the bootstrap url hostname. Used to populate the CA SAN
    extension """
    url = config['exhibitor_bootstrap_ca_url'] or config['bootstrap_url']
    return urlparse(url).hostname or ""


def initialize_exhibitor_ca(final_arguments: Dict[str, Any]):
    reasons = _check(final_arguments)
    if reasons:
        print('[{}] not bootstrapping exhibitor CA: {}'.format(
            __name__, '\n'.join(reasons)))
        final_arguments['exhibitor_ca_certificate'] = ""
        final_arguments['exhibitor_ca_certificate_path'] = "/dev/null"
        return

    package_path = (
        pathlib.Path('/artifacts/packages/dcoscertstrap')
        / (find_package(final_arguments['cluster_packages']) + '.tar.xz'))

    ca_alternative_names = ['127.0.0.1', 'localhost', _get_ca_alt_name(final_arguments)]

    _extract_package(package_path)
    _init_ca(ca_alternative_names)

    # inject
    final_arguments['exhibitor_ca_certificate'] = _read_certificate()
    final_arguments['exhibitor_ca_certificate_path'] = '/tmp/.root-cert.pem'
