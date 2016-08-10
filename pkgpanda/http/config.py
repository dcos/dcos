import os
import tempfile

from pkgpanda import constants


DCOS_ROOT = constants.install_root
DCOS_CONFIG_DIR = constants.config_dir
DCOS_REPO_DIR = constants.repository_base
DCOS_ROOTED_SYSTEMD = False

WORK_DIR = os.path.join(tempfile.gettempdir(), 'pkgpanda_api')
