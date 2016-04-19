local_cache = "/opt/mesosphere/packages"

# TODO: /opt/mesosphere/packages
install_base = "/opt/mesosphere/dcos"
repository_base = "/opt/mesosphere/packages"

RESERVED_UNIT_NAMES = [
    "dcos.target",
    "dcos-download.service",
    "dcos-setup.service"
]
