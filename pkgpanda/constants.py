from pkgpanda.util import is_windows

RESERVED_UNIT_NAMES = [
    "dcos.target",
    "dcos-download.service",
    "dcos-setup.service"
]

if is_windows:
    STATE_DIR_ROOT = 'c:/var/lib/dcos'
    PACKAGES_DIR = "packages"
    PKG_DIR = "c:/pkg"
    config_dir = 'c:/etc/mesosphere'
    install_root = 'c:/opt/mesosphere'
    repository_base = 'c:/opt/mesosphere/' + PACKAGES_DIR
else:
    STATE_DIR_ROOT = '/var/lib/dcos'
    PACKAGES_DIR = "packages"
    PKG_DIR = "/pkg"
    config_dir = '/etc/mesosphere'
    install_root = '/opt/mesosphere'
    repository_base = '/opt/mesosphere/' + PACKAGES_DIR

DCOS_SERVICE_CONFIGURATION_FILE = "dcos-service-configuration.json"
DCOS_SERVICE_CONFIGURATION_PATH = install_root + "/etc/" + DCOS_SERVICE_CONFIGURATION_FILE
SYSCTL_SETTING_KEY = "sysctl"
