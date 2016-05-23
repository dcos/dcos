DCOS_ROOT = '/opt/mesosphere/'
DCOS_CONFIG_DIR = '/etc/mesosphere/'
DCOS_REPO_DIR = '/opt/mesosphere/packages/'
DCOS_ROOTED_SYSTEMD = False

try:
    with open('/etc/mesosphere/setup-flags/repository-url') as f:
        DCOS_BOOTSTRAP_URL = f.read().strip()
except OSError:
    DCOS_BOOTSTRAP_URL = ''

WORK_DIR = '/tmp/pkgpanda_api'
