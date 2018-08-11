from os import sep
from os.path import abspath

from pkgpanda.util import is_windows


GENCONF_DIR = 'genconf'
CONFIG_PATH = GENCONF_DIR + sep + 'config.yaml'
SSH_KEY_PATH = GENCONF_DIR + sep + 'ssh_key'
if is_windows:
    IP_DETECT_PATH = GENCONF_DIR + sep + 'ip-detect.ps1'
else:
    IP_DETECT_PATH = GENCONF_DIR + sep + 'ip-detect'
CLUSTER_PACKAGES_PATH = GENCONF_DIR + sep + 'cluster_packages.json'
SERVE_DIR = GENCONF_DIR + sep + 'serve'
STATE_DIR = GENCONF_DIR + sep + 'state'
BOOTSTRAP_DIR = SERVE_DIR + sep + 'bootstrap'
PACKAGE_LIST_DIR = SERVE_DIR + sep + 'package_lists'
ARTIFACT_DIR = 'artifacts'
CHECK_RUNNER_CMD = abspath('/opt/mesosphere/bin/dcos-check-runner') + ' check'
