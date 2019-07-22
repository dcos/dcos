def gen_tls_artifacts(ca_url, artifacts_path) -> None:
    print('Generating TLS artifacts via CA service: `{}`'.format(ca_url))
    psk_path = Path('/dcoscertstrap.psk')
    psk = ''
    if psk_path.exists():
        psk = psk_path.read_text()


dcos_config_path = Path('/opt/mesosphere/etc/user.config.full.yaml')
dcos_config = yaml.load(dcos_config_path.read_text())

if dcos_config['exhibitor_security']:
    artifacts_path = Path('/var/lib/dcos/exhibitor-tls-artifacts')

    truststore_path = artifacts_path / 'truststore.jks'
    clientstore_path = artifacts_path / 'clientstore.jks'
    serverstore_path = artifacts_path / 'serverstore.jks'

    if not truststore_path.exists() or \
       not clientstore_path.exists() or \
       not serverstore_path.exists():
        # Create Exhibitor TLS artifacts automatically via the CA service.
        print('No Exhibitor TLS artifacts found under `{path}`'.format(
            path=artifacts_path))

        try:
            ca_url = dcos_config['exhibitor_bootstrap_ca_url']
        except KeyError:
            # Infer CA url from bootstrap url.
            bootstrap_url = dcos_config['bootstrap_url']
            if bootstrap_url.startswith('http'):
                boostrap_hostname = str().split(':')[0]
                ca_url = '{host}:{port}'.format(host=bootstrap_hostname, port=443)
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

        gen_tls_artifacts(ca_url, artifacts_path)

    else:
        # Expect TLS artifacts to have been put in place by the operator.
        pass

    exhibitor_env = os.environ.copy()
    exhibitor_env['EXHIBITOR_TLS_TRUSTSTORE_PATH'] = truststore_path
    exhibitor_env['EXHIBITOR_TLS_TRUSTSTORE_PASSWORD'] = 'not-relevant-for-security'
    exhibitor_env['EXHIBITOR_TLS_CLIENT_KEYSTORE_PATH'] = clientstore_path
    exhibitor_env['EXHIBITOR_TLS_CLIENT_KEYSTORE_PASSWORD'] = 'not-relevant-for-security'
    exhibitor_env['EXHIBITOR_TLS_SERVER_KEYSTORE_PATH'] = serverstore_path
    exhibitor_env['EXHIBITOR_TLS_SERVER_KEYSTORE_PASSWORD'] = 'not-relevant-for-security'
    exhibitor_env['EXHIBITOR_TLS_REQUIRE_CLIENT_CERT'] = 'true'
    exhibitor_env['EXHIBITOR_TLS_VERIFY_PEER_CERT'] = 'true'

