import os
import subprocess
import yaml
from pathlib import Path

from start_exhibitor import invoke_detect_ip


TLS_ARTIFACT_LOCATION = '/var/lib/dcos/exhibitor-tls-artifacts'
PRESHAREDKEY_LOCATION = '/dcoscertstrap.psk'


def get_ca_service_url(dcos_config) -> str:
    """
    Get the CA service URL from the DC/OS config.yaml.
    First try to return the `exhibitor_bootstrap_ca_url`.
    If that's not possible try to infer the URL from the
    `bootstrap_url` in case it is an HTTP URL.
    """
    try:
        return dcos_config['exhibitor_bootstrap_ca_url']
    except KeyError:
        # Infer CA url from bootstrap url.
        bootstrap_url = dcos_config['bootstrap_url']

        if bootstrap_url.startswith('http'):
            bootstrap_host = bootstrap_url.split(':')[0]
            return '{host}:{port}'.format(host=bootstrap_host, port=443)

        else:
            # NOTE(tweidner): `bootstrap_url` can be a valid non-HTTP URL.
            message = (
                'ERROR: Failed to infer `exhibitor_bootstrap_ca_url` from '
                '`bootstrap_url` {bootstrap_url}. `bootstrap_url` does not '
                'point to an HTTP server. Consider setting '
                '`exhibitor_bootstrap_ca_url` explicitly, put Exhibitor TLS '
                'artifacts in place under `{artifacts_path}` or disable '
                'Exhibitor TLS via `exhibitor_security: false`.'
            ).format(
                bootstrap_url=bootstrap_url,
                artifacts_path=artifacts_path,
            )
            print(message)
            sys.exit(1)


def gen_tls_artifacts(ca_url, artifacts_path) -> None:
    """
    Contact the CA service to sign the generated TLS artifacts.
    Write the signed Exhibitor TLS artifacts to the file system.
    """
    print('Generating TLS artifacts via CA service: `{}`'.format(ca_url))

    # Fail early if IP detect script does not properly resolve yet.
    ip = invoke_detect_ip()

    psk_path = Path(PRESHAREDKEY_LOCATION)
    if psk_path.exists():
        psk = psk_path.read_text()
    else:
        # Empty PSK results in any CSR being signed by the CA service.
        psk = ''

    print('Initiating CA service client structure')
    result = subprocess.check_output(
        args=['/opt/mesosphere/bin/dcoscertstrap', 'init-client'],
        stderr=subprocess.STDOUT,
    )
    print(result.stdout.decode())

    print('Making Certificate Signing Request with IP {}'.format(ip))
    result = subprocess.check_output(
        args=[
            '/opt/mesosphere/bin/dcoscertstrap', 'csr',
            '--url', '',
            '--psk', '',
            '--common-name', 'client',
            '--country', 'US',
            '--state', 'CA',
            '--locality', 'San Francisco',
            '--email-addresses', 'security@mesosphere.com',
            '--sans', '{},exhibitor,localhost,127.0.0.1'.format(ip),
        ],
        stderr=subprocess.STDOUT,
    )
    print(result.stdout.decode())

    print('Writing TLS artifacts to {}'.format(artifacts_path))
    result = subprocess.check_output(
        args=[
            '/opt/mesosphere/bin/dcoscertstrap', 'out',
            '--all',
            '--path', '{}'.format(artifacts_path),
        ],
        stderr=subprocess.STDOUT,
    )
    print(result.stdout.decode())


dcos_config_path = Path('/opt/mesosphere/etc/user.config.full.yaml')
dcos_config = yaml.load(dcos_config_path.read_text())

if dcos_config['exhibitor_security']:
    artifacts_path = Path(TLS_ARTIFACT_LOCATION)
    truststore_path = Path(artifacts_path / 'truststore.jks')
    clientstore_path = Path(artifacts_path / 'clientstore.jks')
    serverstore_path = Path(artifacts_path / 'serverstore.jks')

    exhibitor_env = os.environ.copy()
    exhibitor_env['EXHIBITOR_TLS_TRUSTSTORE_PATH'] = truststore_path
    exhibitor_env['EXHIBITOR_TLS_TRUSTSTORE_PASSWORD'] = 'not-relevant-for-security'
    exhibitor_env['EXHIBITOR_TLS_CLIENT_KEYSTORE_PATH'] = clientstore_path
    exhibitor_env['EXHIBITOR_TLS_CLIENT_KEYSTORE_PASSWORD'] = 'not-relevant-for-security'
    exhibitor_env['EXHIBITOR_TLS_SERVER_KEYSTORE_PATH'] = serverstore_path
    exhibitor_env['EXHIBITOR_TLS_SERVER_KEYSTORE_PASSWORD'] = 'not-relevant-for-security'
    exhibitor_env['EXHIBITOR_TLS_REQUIRE_CLIENT_CERT'] = 'true'
    exhibitor_env['EXHIBITOR_TLS_VERIFY_PEER_CERT'] = 'true'

    if not truststore_path.exists() or \
       not clientstore_path.exists() or \
       not serverstore_path.exists():
        print('No Exhibitor TLS artifacts found under `{path}`'.format(
            path=artifacts_path))

        ca_url = get_ca_service_url(dcos_config)
        gen_tls_artifacts(ca_url, artifacts_path)
