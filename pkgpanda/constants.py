from pkgpanda.util import is_windows

RESERVED_UNIT_NAMES = [
    "dcos.target",
    "dcos-download.service",
    "dcos-setup.service"
]

if is_windows:
    # windows specific directory locations
    # Note that these are not yet final and are placeholders
    STATE_DIR_ROOT = 'c:\\var\\lib\\dcos'
    PKG_DIR = "c:\\pkg"
    config_dir = 'c:\\etc\\mesosphere'
    install_root = 'c:\\opt\\mesosphere'
    repository_base = install_root + '\\packages'

    DOCKERFILE_DIR = 'docker.windows\\'

    # Windows specific configuration files
    # System configuration on windows is quite different
    # so these files will be quite different once fully ported
    dcos_config_yaml = 'dcos-config-windows.yaml'
    dcos_services_yaml = 'dcos-services-windows.yaml'
    cloud_config_yaml = 'cloud-config-windows.yaml'
else:
    STATE_DIR_ROOT = '/var/lib/dcos'
    PKG_DIR = "/pkg"
    DOCKERFILE_DIR = 'docker/'
    config_dir = '/etc/mesosphere'
    install_root = '/opt/mesosphere'
    repository_base = install_root + '/packages'

    # Non-windows specific configuration files.
    dcos_config_yaml = 'dcos-config.yaml'
    dcos_services_yaml = 'dcos-services.yaml'
    cloud_config_yaml = 'cloud-config.yaml'

DCOS_SERVICE_CONFIGURATION_FILE = "dcos-service-configuration.json"
DCOS_SERVICE_CONFIGURATION_PATH = install_root + "/etc/" + DCOS_SERVICE_CONFIGURATION_FILE
SYSCTL_SETTING_KEY = "sysctl"
