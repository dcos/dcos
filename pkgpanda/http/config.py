from pkgpanda import constants


DCOS_ROOT = constants.install_root
DCOS_CONFIG_DIR = constants.config_dir
DCOS_REPO_DIR = constants.repository_base
DCOS_ROOTED_SYSTEMD = False

try:
    with open('/etc/mesosphere/setup-flags/repository-url') as f:
        DCOS_BOOTSTRAP_URL = f.read().strip()
except OSError:
    DCOS_BOOTSTRAP_URL = ''

WORK_DIR = '/tmp/pkgpanda_api'
