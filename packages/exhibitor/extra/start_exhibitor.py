#!/opt/mesosphere/bin/python
import os
import socket
import subprocess
import sys
from pathlib import Path
from subprocess import CalledProcessError, check_call, check_output


ZK_VAR_DIR = '/var/lib/dcos/exhibitor/zookeeper'
ZK_SNAPSHOTS = os.path.join(ZK_VAR_DIR, 'snapshot')
ZK_TRANSACTIONS = os.path.join(ZK_VAR_DIR, 'transactions')

TLS_ARTIFACT_LOCATION = '/var/lib/dcos/exhibitor-tls-artifacts'
CSR_SERVICE_CERT_PATH = '/dcoscertstrap-root-cert.pem'
PRESHAREDKEY_LOCATION = '/dcoscertstrap.psk'
EXHIBITOR_TLS_TMP_DIR = '/var/lib/dcos/exhibitor'


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
        psk = '""'

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


def get_var_assert_set(name):
    if name not in os.environ:
        print('ERROR: "{}" must be set'.format(name))
        sys.exit(1)

    return os.environ[name]


def write_str(filename, contents):
    with open(filename, 'w') as f:
        f.write(contents)


# TODO(cmaloney): Pull out into a utility library. Copied in both gen_resolvconf.py
# and here.
def invoke_detect_ip():
    try:
        ip = check_output(
            ['/opt/mesosphere/bin/detect_ip']).strip().decode('utf-8')
    except CalledProcessError as e:
        print("check_output exited with {}".format(e))
        sys.exit(1)
    try:
        socket.inet_aton(ip)
        return ip
    except socket.error as e:
        print(
            "inet_aton exited with {}. {} is not a valid IPv4 address".format(e, ip))
        sys.exit(1)


detected_ip = invoke_detect_ip()

# Make the zk conf directory (exhibitor assumes the dir exists)
check_call(['mkdir', '-p', '/var/lib/dcos/exhibitor/conf/'])

# From https://zookeeper.apache.org/doc/r3.4.13/zookeeperAdmin.html:
# "The data stored in these [snapshot and log] files is not encrypted. In the
# case of storing sensitive data in ZooKeeper, necessary measures need to be
# taken to prevent unauthorized access."
os.makedirs(ZK_SNAPSHOTS, 0o700, exist_ok=True)
os.makedirs(ZK_TRANSACTIONS, 0o700, exist_ok=True)
os.chmod(ZK_VAR_DIR, 0o700)

# On some systems /tmp is mounted as noexec. Make zookeeper write its JNA
# libraries to a path we control instead. See DCOS-11056
jna_tmpdir = get_var_assert_set('JNA_TMP_DIR')
check_call(['mkdir', '-p', jna_tmpdir])

# TODO(cmaloney): Move exhibitor_defaults to a temp runtime conf dir.
# Base for building up the command line
exhibitor_cmdline = [
    'java',
    '-Djava.util.prefs.systemRoot=/var/lib/dcos/exhibitor/',
    '-Djava.util.prefs.userRoot=/var/lib/dcos/exhibitor/',
    '-Duser.home=/var/lib/dcos/exhibitor/',
    '-Duser.dir=/var/lib/dcos/exhibitor/',
    '-Djna.tmpdir=%s' % jna_tmpdir,
    '-jar', '$PKG_PATH/usr/exhibitor/exhibitor.jar',
    '--port', '8181',
    '--defaultconfig', '/run/dcos_exhibitor/exhibitor_defaults.conf',
    '--hostname', detected_ip
]

# Optionally pick up web server security configuration.
if os.path.exists('/opt/mesosphere/etc/exhibitor_web.xml') and \
        os.path.exists('/opt/mesosphere/etc/exhibitor_realm'):
    exhibitor_cmdline.extend([
        '--security', '/opt/mesosphere/etc/exhibitor_web.xml',
        '--realm', 'DCOS:/opt/mesosphere/etc/exhibitor_realm',
        '--remoteauth', 'basic:admin'
    ])

zookeeper_cluster_size = int(open('/opt/mesosphere/etc/master_count').read().strip())

check_ms = 30000
if zookeeper_cluster_size == 1:
    check_ms = 2000

# Write out base exhibitor configuration
write_str('/run/dcos_exhibitor/exhibitor_defaults.conf', """
# These Exhibitor properties are used to first initialize the config stored in
# an empty shared storage location. Any subsequent invocations of Exhibitor will
# ignore these properties and use the config found in shared storage.
zookeeper-data-directory={zookeeper_data_dir}
zookeeper-install-directory=/opt/mesosphere/active/exhibitor/usr/zookeeper
zookeeper-log-directory={zookeeper_log_dir}
zookeeper-config-directory=/var/lib/dcos/exhibitor/conf
zookeeper-pid-path=/var/lib/dcos/exhibitor/zk.pid
log-index-directory={zookeeper_log_dir}
cleanup-period-ms=300000
check-ms={check_ms}
backup-period-ms=600000
client-port=2181
cleanup-max-files=20
backup-max-store-ms=21600000
connect-port=2888
observer-threshold=0
election-port=3888
zoo-cfg-extra=tickTime\=2000&initLimit\=10&syncLimit\=5&quorumListenOnAllIPs\=true&maxClientCnxns\=0&autopurge.snapRetainCount\=5&autopurge.purgeInterval\=6
auto-manage-instances-settling-period-ms=0
auto-manage-instances=1
auto-manage-instances-fixed-ensemble-size={zookeeper_cluster_size}
""".format(
    zookeeper_cluster_size=zookeeper_cluster_size,
    check_ms=check_ms,
    zookeeper_data_dir=ZK_SNAPSHOTS,
    zookeeper_log_dir=ZK_TRANSACTIONS,
))

write_str('/var/lib/dcos/exhibitor/conf/log4j.properties', """
log4j.rootLogger=INFO, journal

log4j.appender.journal=de.bwaldvogel.log4j.SystemdJournalAppenderWithLayout
log4j.appender.journal.logStacktrace=true
log4j.appender.journal.logThreadName=true
log4j.appender.journal.logLoggerName=true
log4j.appender.journal.layout=org.apache.log4j.EnhancedPatternLayout
log4j.appender.journal.layout.ConversionPattern=[myid:%X{myid}] %-5p [%t:%C{1}@%L] - %m%n%throwable
""")

# Add backend specific arguments
exhibitor_backend = get_var_assert_set('EXHIBITOR_BACKEND')
if exhibitor_backend == 'STATIC':
    print("Exhibitor configured for static ZK ensemble")
    # In case of a static Exhibitor backend DC/OS configuration we can check
    # that the value for the hostname set by invoking the ip-detect script is
    # indeed included in the master list.
    # https://jira.mesosphere.com/browse/COPS-3485
    exhibitor_staticensemble = get_var_assert_set('EXHIBITOR_STATICENSEMBLE')
    master_ips = [i.split(':')[1] for i in exhibitor_staticensemble.split(',')]
    if detected_ip not in master_ips:
        message = (
            "ERROR: ip-detect returned {master_ip}. "
            "{master_ip} is not in the configured list of masters."
        ).format(master_ip=detected_ip)
        print(message)
        sys.exit(1)
    exhibitor_cmdline += [
        '--configtype=static',
        '--staticensemble', get_var_assert_set('EXHIBITOR_STATICENSEMBLE')
    ]
elif zookeeper_cluster_size == 1:
    print("Exhibitor configured for single master/static backend")
    # A Zookeeper cluster size of 1 is a special case regarding the Exhibitor backend.
    # It will always output in a static backend independent of the DC/OS configuration.
    # This allows for skipping exhibitor.wait() logic that is responsible for waiting
    # for Exhibitor configuration change from standalone mode to ensemble mode.
    # https://jira.mesosphere.com/browse/DCOS-6147
    exhibitor_cmdline += [
        '--configtype=static',
        '--staticensemble=1:' + detected_ip
    ]
elif exhibitor_backend == 'AWS_S3':
    print("Exhibitor configured for AWS S3")
    exhibitor_cmdline += [
        '--configtype=s3',
        '--s3config', get_var_assert_set("AWS_S3_BUCKET") +
        ':' + get_var_assert_set("AWS_S3_PREFIX"),
        '--s3region', get_var_assert_set("AWS_REGION"),
        '--s3backup', 'false',
    ]

    # If there are explicit s3 credentials, add an --s3credentials flag
    if os.path.exists('/opt/mesosphere/etc/exhibitor.properties'):
        exhibitor_cmdline += ['--s3credentials', '/opt/mesosphere/etc/exhibitor.properties']
elif exhibitor_backend == 'AZURE':
    print("Exhibitor configured for Azure")
    exhibitor_cmdline += [
        '--configtype=azure',
        '--azureconfig', get_var_assert_set(
            'AZURE_CONTAINER') + ':' + get_var_assert_set('AZURE_PREFIX'),
        '--azurecredentials', '/opt/mesosphere/etc/exhibitor.properties',
    ]
elif exhibitor_backend == 'GCE':
    print("Exhibitor configured for GCE")
    exhibitor_cmdline += [
        '--configtype=gcs',
        '--gcsconfig={}:{}'.format(
            get_var_assert_set('GCS_BUCKET_NAME', 'GCE_BUCKET_NAME'))
    ]
elif exhibitor_backend == 'ZK':
    print("Exhibitor configured for Zookeeper")
    exhibitor_cmdline += [
        '--configtype=zookeeper',
        '--zkconfigconnect={}'.format(get_var_assert_set('ZK_CONFIG_CONNECT')),
        '--zkconfigzpath={}'.format(get_var_assert_set('ZK_CONFIG_ZPATH'))
    ]
elif exhibitor_backend == 'SHARED_FS':
    print("Exhibitor configured for shared filesystem")
    exhibitor_cmdline += [
        '--configtype=file',
        '--fsconfigdir', get_var_assert_set('EXHIBITOR_FSCONFIGDIR')
    ]
else:
    print("ERROR: No known exhibitor backend:", exhibitor_backend)
    sys.exit(1)


exhibitor_env = os.environ.copy()

if exhibitor_env['EXHIBITOR_TLS_ENABLED'] == 'false':
    print('Exhibitor TLS explicitly disabled')
else:
    print('Enabling Exhibitor TLS')
    artifacts_path = Path(TLS_ARTIFACT_LOCATION)
    truststore_path = Path(artifacts_path / 'truststore.jks')
    clientstore_path = Path(artifacts_path / 'clientstore.jks')
    serverstore_path = Path(artifacts_path / 'serverstore.jks')

    def _exists(artifact_path: Path):
        exists = artifact_path.exists()
        if not exists:
            print('{} not found.'.format(artifact_path))
        return exists

    artifacts = list(map(_exists, [truststore_path, serverstore_path, clientstore_path]))

    if not all(artifacts):
        print('WARNING: Not all Exhibitor TLS artifacts found in `{path}`.'.format(
            path=artifacts_path))

        if any(artifacts):
            print('ERROR: Invalid configuration, partial Exhibitor TLS artifacts found.')
            sys.exit(1)

        exhibitor_bootstrap_ca_url = exhibitor_env['EXHIBITOR_BOOTSTRAP_CA_URL']
        bootstrap_url = exhibitor_env['BOOTSTRAP_URL']
        try:
            ca_url = get_ca_url(exhibitor_bootstrap_ca_url, bootstrap_url)
        except ValueError as exc:
            print(str(exc))
            sys.exit(1)

        print('Generating TLS artifacts via CSR service: `{}`'.format(ca_url))
        gen_tls_artifacts(ca_url, artifacts_path)

    exhibitor_env['EXHIBITOR_TLS_TRUSTSTORE_PATH'] = truststore_path
    exhibitor_env['EXHIBITOR_TLS_TRUSTSTORE_PASSWORD'] = 'not-relevant-for-security'
    exhibitor_env['EXHIBITOR_TLS_CLIENT_KEYSTORE_PATH'] = clientstore_path
    exhibitor_env['EXHIBITOR_TLS_CLIENT_KEYSTORE_PASSWORD'] = 'not-relevant-for-security'
    exhibitor_env['EXHIBITOR_TLS_SERVER_KEYSTORE_PATH'] = serverstore_path
    exhibitor_env['EXHIBITOR_TLS_SERVER_KEYSTORE_PASSWORD'] = 'not-relevant-for-security'
    exhibitor_env['EXHIBITOR_TLS_REQUIRE_CLIENT_CERT'] = 'true'
    exhibitor_env['EXHIBITOR_TLS_VERIFY_PEER_CERT'] = 'true'

# Start exhibitor
print("Running exhibitor as command:", exhibitor_cmdline)
sys.stdout.flush()
os.execve('/opt/mesosphere/bin/java', exhibitor_cmdline, exhibitor_env)
