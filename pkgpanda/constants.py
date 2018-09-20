import os

from pkgpanda.util import is_windows

RESERVED_UNIT_NAMES = [
    "dcos.target",
    "dcos-download.service",
    "dcos-setup.service"
]

if is_windows:
    # windows specific directory locations
    # Note that these are not yet final and are placeholders
    DOCKERFILE_DIR = 'docker.windows' + os.sep

    # Windows specific configuration files
    # System configuration on windows is quite different
    # so these files will be quite different once fully ported
    dcos_config_yaml = 'dcos-config-windows.yaml'
    dcos_services_yaml = 'dcos-services-windows.yaml'
    cloud_config_yaml = 'cloud-config-windows.yaml'
else:
    DOCKERFILE_DIR = 'docker' + os.sep

    # Non-windows specific configuration files.
    dcos_config_yaml = 'dcos-config.yaml'
    dcos_services_yaml = 'dcos-services.yaml'
    cloud_config_yaml = 'cloud-config.yaml'

STATE_DIR_ROOT = os.path.abspath('/var/lib/dcos')
PKG_DIR = os.path.abspath("/pkg")
config_dir = os.path.abspath('/etc/mesosphere')
install_root = os.path.abspath('/opt/mesosphere')
repository_base = install_root + os.sep + 'packages'
systemd_system_root = os.path.abspath('/etc/systemd/system')
profile_dir = os.path.abspath('/etc/profile.d')

DCOS_SERVICE_CONFIGURATION_FILE = "dcos-service-configuration.json"
DCOS_SERVICE_CONFIGURATION_PATH = install_root + os.sep + "etc" + os.sep + DCOS_SERVICE_CONFIGURATION_FILE
SYSCTL_SETTING_KEY = "sysctl"
