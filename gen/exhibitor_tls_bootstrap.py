import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from gen.exceptions import ExhibitorTLSBootstrapError


PACKAGE_NAME = 'dcos-bootstrap-ca'
BINARY_PATH = '/genconf/bin'
CA_PATH = '/genconf/ca'


def _check(config: Dict[str, Any]) -> Tuple[List[str], bool]:
    """
    Current constraints are:
        config.yaml:
            - exhibitor_tls_enabled == True,
            - bootstrap_url must not be a local path
                This is necessary to prevent this orchestration
                from running when gen is not executed on a proper
                bootstrap node. This is a soft failure
            - master_discovery must be static
            - DC/OS variant must be enterprise
            - exhibitor_bootstrap_ca_url must not be set. When set,
              it indicates that the ca service will be initialized and
              started outside of gen.
    Hard failures help us to fail early when exhibitor_tls_required == True.
    Soft "failures" allow CA initialization to occur outside of genconf.
    """
    checks = [
        (lambda: config.get('exhibitor_tls_enabled') == 'true',
         'Exhibitor security is disabled', True),
        (lambda: config['master_discovery'] == 'static',
         'Only static master discovery is supported', True),
        (lambda: config['dcos_variant'] == 'enterprise',
         'Exhibitor security is an enterprise feature', True),
        (lambda: urlparse(config['bootstrap_url']).scheme != 'file',
         'CA init in gen is only supported when using a remote'
         ' bootstrap node', False),
        (lambda: 'exhibitor_bootstrap_ca_url' in config,
         'Custom CA url has been specified, not initializing CA', False)
    ]

    reasons = []

    hard_failure = False
    for (func, reason, hard) in checks:
        if not func():
            if hard:
                hard_failure = True
            reasons.append(reason)

    return reasons, hard_failure


def _find_package(packages_json: str) -> str:
    packages = json.loads(packages_json)
    for package in packages:
        if package.startswith(PACKAGE_NAME):
            return package
    raise Exception('{} package is not present'.format(PACKAGE_NAME))


def _extract_package(package_path: str) -> None:
    """ Extracts the dcos-bootstrap-ca package from the local pkgpanda
    repository """
    Path(BINARY_PATH).mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(['tar', '-xJf', package_path, '-C', td])

        shutil.move(
            Path(td) / 'bin' / PACKAGE_NAME,
            Path(BINARY_PATH) / PACKAGE_NAME)


def _init_ca(alt_names: List[str]) -> None:
    """ Initializes the CA (generates a private key and self signed
    certificate CA extensions) if the resulting files do not already exist """
    root_ca_paths = [
        Path(CA_PATH) / 'root-cert.pem', Path(CA_PATH) / 'root-key.pem']
    if not all(map(lambda p: p.exists(), root_ca_paths)):
        try:
            Path(CA_PATH).mkdir(mode=0o700)
        except FileExistsError:
            if not Path(CA_PATH).is_dir():
                raise
            # if the file exist, change permissions and take ownership
            Path(CA_PATH).chmod(mode=0o700)
            os.chown(CA_PATH, os.getuid(), os.getgid())
        cmd_path = Path(BINARY_PATH) / PACKAGE_NAME
        subprocess.run([
            str(cmd_path), '-d', CA_PATH, 'init-ca', '--sans', ','.join(alt_names)
        ])
    else:
        print('[{}] CA files already exist'.format(__name__))


def _get_ca_alt_name(config: Dict[str, Any]) -> str:
    """ Gets the bootstrap url hostname. Used to populate the CA SAN
    extension """
    url = config['exhibitor_bootstrap_ca_url'] or config['bootstrap_url']
    return urlparse(url).hostname or ""


def initialize_exhibitor_ca(final_arguments: Dict[str, Any]) -> None:
    if final_arguments['platform'] != 'onprem':
        return

    reasons, hard_failure = _check(final_arguments)
    if reasons:
        # Exhibitor TLS is required, fail hard
        if final_arguments.get('exhibitor_tls_required') == 'true' and hard_failure:
            raise ExhibitorTLSBootstrapError(errors=reasons)
        print('[{}] not bootstrapping exhibitor CA: {}'.format(
            __name__, '\n'.join(reasons)))
        final_arguments['exhibitor_ca_certificate'] = ""
        final_arguments['exhibitor_ca_certificate_path'] = "/dev/null"
        return

    package_filename = _find_package(
        final_arguments['cluster_packages']) + '.tar.xz'
    package_path = Path('/artifacts/packages') / PACKAGE_NAME / package_filename

    ca_alternative_names = ['127.0.0.1', 'localhost',
                            'exhibitor', _get_ca_alt_name(final_arguments)]

    _extract_package(package_path)
    _init_ca(ca_alternative_names)

    root_cert_path = Path(CA_PATH) / 'root-cert.pem'
    final_arguments['exhibitor_ca_certificate'] = root_cert_path.read_text(
        encoding='ascii')
    final_arguments['exhibitor_ca_certificate_path'] = '/tmp/root-cert.pem'
