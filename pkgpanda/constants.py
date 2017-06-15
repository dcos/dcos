RESERVED_UNIT_NAMES = [
    "dcos.target",
    "dcos-download.service",
    "dcos-setup.service"
]

DCOS_SERVICE_CONFIGURATION_FILE = "dcos-service-configuration.json"
DCOS_SERVICE_CONFIGURATION_PATH = "/opt/mesosphere/etc/" + DCOS_SERVICE_CONFIGURATION_FILE
SYSCTL_SETTING_KEY = "sysctl"

STATE_DIR_ROOT = '/var/lib/dcos'

config_dir = '/etc/mesosphere'
install_root = '/opt/mesosphere'
repository_base = '/opt/mesosphere/packages'
