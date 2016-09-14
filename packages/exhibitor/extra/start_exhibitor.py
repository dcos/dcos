#!/opt/mesosphere/bin/python
import os
import socket
import sys
from subprocess import CalledProcessError, check_call, check_output


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
check_call(['mkdir', '-p', '/var/lib/dcos/exhibitor/conf/', '/var/lib/dcos/exhibitor/zookeeper/transactions'])

# TODO(cmaloney): Move exhibitor_defaults to a temp runtime conf dir.
# Base for building up the command line
exhibitor_cmdline = [
    'java',
    '-Djava.util.prefs.systemRoot=/var/lib/dcos/exhibitor/',
    '-Djava.util.prefs.userRoot=/var/lib/dcos/exhibitor/',
    '-Duser.home=/var/lib/dcos/exhibitor/',
    '-Duser.dir=/var/lib/dcos/exhibitor/',
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
zookeeper-data-directory=/var/lib/dcos/exhibitor/zookeeper/snapshot
zookeeper-install-directory=/opt/mesosphere/active/exhibitor/usr/zookeeper
zookeeper-log-directory=/var/lib/dcos/exhibitor/zookeeper/transactions
zookeeper-config-directory=/var/lib/dcos/exhibitor/conf
zookeeper-pid-path=/var/lib/dcos/exhibitor/zk.pid
log-index-directory=/var/lib/dcos/exhibitor/zookeeper/transactions
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
    check_ms=check_ms
))

write_str('/var/lib/dcos/exhibitor/conf/log4j.properties', """
log4j.rootLogger=INFO, journal, console

log4j.appender.journal=de.bwaldvogel.log4j.SystemdJournalAppender
log4j.appender.journal.logStacktrace=true
log4j.appender.journal.logThreadName=true
log4j.appender.journal.logLoggerName=true

log4j.appender.console=org.apache.log4j.ConsoleAppender
log4j.appender.console.Threshold=INFO
log4j.appender.console.layout=org.apache.log4j.PatternLayout
log4j.appender.console.layout.ConversionPattern=%d{ISO8601} [myid:%X{myid}] - %-5p [%t:%C{1}@%L] - %m%n
""")

# Add backend specific arguments
exhibitor_backend = get_var_assert_set('EXHIBITOR_BACKEND')
if zookeeper_cluster_size == 1:
    print("Exhibitor configured for single master/static backend")
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
elif exhibitor_backend == 'STATIC':
    print("Exhibitor configured for static ZK ensemble")
    exhibitor_cmdline += [
        '--configtype=static',
        '--staticensemble', get_var_assert_set('EXHIBITOR_STATICENSEMBLE')
    ]
else:
    print("ERROR: No known exhibitor backend:", exhibitor_backend)
    sys.exit(1)

# Start exhibitor
print("Running exhibitor as command:", exhibitor_cmdline)
sys.stdout.flush()
os.execv('/opt/mesosphere/bin/java', exhibitor_cmdline)
