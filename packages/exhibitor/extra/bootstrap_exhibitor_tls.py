import os
import socket
import subprocess
import sys

from pathlib import Path

TLS_ARTIFACT_LOCATION = '/var/lib/dcos/exhibitor-tls-artifacts'
CSR_SERVICE_CERT_PATH = '/tmp/.root-cert.pem'
PRESHAREDKEY_LOCATION = '/root/.dcoscertstrap_psk'
EXHIBITOR_TLS_TMP_DIR = '/var/lib/dcos/exhibitor/.pki'


def invoke_detect_ip():
    try:
        ip = subprocess.check_output(
            ['/opt/mesosphere/bin/detect_ip']).strip().decode('utf-8')
    except subprocess.CalledProcessError as e:
        print("check_output exited with {}".format(e))
        sys.exit(1)
    try:
        socket.inet_aton(ip)
        return ip
    except socket.error as e:
        print(
            "inet_aton exited with {}. {} is not a valid IPv4 address".format(e, ip))
        sys.exit(1)


def get_ca_url(exhibitor_bootstrap_ca_url, bootstrap_url) -> str:
    if exhibitor_bootstrap_ca_url:
        print('Using `exhibitor_bootstrap_ca_url` config parameter.')
        return exhibitor_bootstrap_ca_url
    else:
        print('Inferring `exhibitor_bootstrap_ca_url` from `bootstrap_url`.')
        try:
            protocol, url = bootstrap_url.split('://')
        except ValueError as exc:
            message = (
                'Failed to calculate `exhibitor_bootstrap_ca_url` from '
                '`bootstrap_url` {bootstrap_url}. Could not determine '
                '`bootstrap_url` protocol.'
            ).format(bootstrap_url=bootstrap_url)
            raise ValueError(message) from exc

        if protocol == 'http' or protocol == 'https':
            bootstrap_host = url.split(':')[0]
            return 'https://{host}:{port}'.format(host=bootstrap_host, port=443)

        message = (
            'Failed to calculcate `exhibitor_bootstrap_ca_url` from `bootstrap_url`. '
            '`bootstrap_url` {bootstrap_url} does not point to an HTTP web server. '
            'Consider setting parameter `exhibitor_bootstrap_ca_url` explicitly.'
        ).format(bootstrap_url=bootstrap_url)
        raise ValueError(message)


def gen_tls_artifacts(ca_url, artifacts_path) -> None:
    """
    Contact the CA service to sign the generated TLS artifacts.
    Write the signed Exhibitor TLS artifacts to the file system.
    """
    # Fail early if IP detect script does not properly resolve yet.
    ip = invoke_detect_ip()

    psk_path = Path(PRESHAREDKEY_LOCATION)
    if psk_path.exists():
        psk = psk_path.read_text()
    else:
        # Empty PSK outputs in any CSR being signed by the CA service.
        psk = ''

    server_entity = 'exhibitor-server'
    client_entity = 'exhibitor-client'

    print('Initiating {} end entity.'.format(server_entity))
    output = subprocess.check_output(
        args=[
            '/opt/mesosphere/bin/dcoscertstrap',
            '--output-dir', str(EXHIBITOR_TLS_TMP_DIR),
            'init-entity', server_entity,
        ],
        stderr=subprocess.STDOUT,
    )
    print(output.decode())

    print('Initiating {} end entity.'.format(client_entity))
    output = subprocess.check_output(
        args=[
            '/opt/mesosphere/bin/dcoscertstrap',
            '--output-dir', str(EXHIBITOR_TLS_TMP_DIR),
            'init-entity', client_entity,
        ],
        stderr=subprocess.STDOUT,
    )
    print(output.decode())

    print('Making CSR for {} with IP {}'.format(server_entity, ip))
    output = subprocess.check_output(
        args=[
            '/opt/mesosphere/bin/dcoscertstrap', 'csr', server_entity,
            '--output-dir', str(EXHIBITOR_TLS_TMP_DIR),
            '--url', ca_url,
            '--ca', str(CSR_SERVICE_CERT_PATH),
            '--psk', psk,
            '--sans', '{},localhost,127.0.0.1'.format(ip),
        ],
        stderr=subprocess.STDOUT,
    )
    print(output.decode())

    print('Making CSR for {} with IP {}'.format(client_entity, ip))
    output = subprocess.check_output(
        args=[
            '/opt/mesosphere/bin/dcoscertstrap', 'csr', client_entity,
            '--output-dir', str(EXHIBITOR_TLS_TMP_DIR),
            '--url', ca_url,
            '--ca', str(CSR_SERVICE_CERT_PATH),
            '--psk', psk,
            '--sans', '{},localhost,127.0.0.1'.format(ip),
        ],
        stderr=subprocess.STDOUT,
    )
    print(output.decode())

    print('Writing TLS artifacts to {}'.format(artifacts_path))
    output = subprocess.check_output(
        args=[
            '/opt/mesosphere/bin/dcoscertstrap', 'create-exhibitor-artifacts',
            '--output-dir', str(EXHIBITOR_TLS_TMP_DIR),
            '--ca', str(CSR_SERVICE_CERT_PATH),
            '--client-entity', client_entity,
            '--server-entity', server_entity,
            '--artifacts-directory', '{}'.format(artifacts_path),
        ],
        stderr=subprocess.STDOUT,
    )
    print(output.decode())


def main():
    exhibitor_env = os.environ.copy()

    if exhibitor_env['EXHIBITOR_TLS_ENABLED'] == 'false':
        return

    if os.path.exists(TLS_ARTIFACT_LOCATION):
        return

    print('Bootstrapping exhibitor TLS')
    exhibitor_bootstrap_ca_url = exhibitor_env['EXHIBITOR_BOOTSTRAP_CA_URL']
    bootstrap_url = exhibitor_env['BOOTSTRAP_URL']

    try:
        ca_url = get_ca_url(exhibitor_bootstrap_ca_url, bootstrap_url)
    except ValueError as exc:
        print(str(exc))
        sys.exit(1)

    gen_tls_artifacts(ca_url, Path(TLS_ARTIFACT_LOCATION))
