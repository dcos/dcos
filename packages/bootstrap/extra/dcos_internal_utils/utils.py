try:
    import fcntl
except ImportError:
    pass
import json
import logging
import os
import platform
import socket
import stat
import subprocess
import sys
import tempfile

is_windows = platform.system() == "Windows"

if not is_windows:
    assert 'fcntl' in sys.modules

log = logging.getLogger(__name__)


# Copied from pkgpanda/util.py#L257-L262
def load_json(filename):
    try:
        with open(filename) as f:
            return json.load(f)
    except ValueError as ex:
        raise ValueError("Invalid JSON in {0}: {1}".format(filename, ex)) from ex


def read_file_line(filename):
    with open(filename, 'r') as f:
        return f.read().strip()


# Copied from pkgpanda/util.py#L292
def write_string(filename, data):
    """
    Write a string to a file.
    Overwrite any data in that file.

    We use an atomic write practice of creating a temporary file and then
    moving that temporary file to the given ``filename``. This prevents race
    conditions such as the file being read by another process after it is
    opened here but not yet written to.

    It also prevents us from creating or truncating a file before we fail to
    write data to it because of low disk space.

    If no file already exists at ``filename``, the new file is created with
    permissions 0o644.
    """
    prefix = os.path.basename(filename)
    tmp_file_dir = os.path.dirname(os.path.realpath(filename))
    fd, temporary_filename = tempfile.mkstemp(prefix=prefix, dir=tmp_file_dir)

    try:
        permissions = os.stat(filename).st_mode
    except FileNotFoundError:
        permissions = 0o644

    try:
        try:
            os.write(fd, data.encode())
        finally:
            os.close(fd)
        os.chmod(temporary_filename, stat.S_IMODE(permissions))
        os.replace(temporary_filename, filename)
    except Exception:
        os.remove(temporary_filename)
        raise


# Copied from gen/calc.py#L87-L102
def valid_ipv4_address(ip):
    try:
        socket.inet_pton(socket.AF_INET, ip)
        return True
    except OSError:
        return False
    except TypeError:
        return False


# Copied from gen/calc.py#L87-L102
def validate_ipv4_addresses(ips: list):
    invalid_ips = []
    for ip in ips:
        if not valid_ipv4_address(ip):
            invalid_ips.append(ip)
    assert not invalid_ips, 'Invalid IPv4 addresses in list: {}'.format(', '.join(invalid_ips))


def detect_ip():
    cmd = ['/opt/mesosphere/bin/detect_ip']
    machine_ip = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('ascii').strip()
    validate_ipv4_addresses([machine_ip])
    return machine_ip


class Directory:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        log.info('Opening {}'.format(self.path))
        self.fd = os.open(self.path, os.O_RDONLY)
        log.info('Opened {} with fd {}'.format(self.path, self.fd))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        log.info('Closing {} with fd {}'.format(self.path, self.fd))
        os.close(self.fd)

    def lock(self):
        return Flock(self.fd, fcntl.LOCK_EX)


class Flock:
    def __init__(self, fd, op):
        (self.fd, self.op) = (fd, op)

    def __enter__(self):
        log.info('Locking fd {}'.format(self.fd))
        # If the fcntl() fails, an IOError is raised.
        fcntl.flock(self.fd, self.op)
        log.info('Locked fd {}'.format(self.fd))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        log.info('Unlocked fd {}'.format(self.fd))


# Copied from pkgpanda/constants.py
if is_windows:
    # windows specific directory locations
    # Note that these are not yet final and are placeholders
    install_root = 'c:\\opt\\mesosphere'
else:
    install_root = '/opt/mesosphere'

DCOS_SERVICE_CONFIGURATION_FILE = "dcos-service-configuration.json"
DCOS_SERVICE_CONFIGURATION_PATH = install_root + "/etc/" + DCOS_SERVICE_CONFIGURATION_FILE
SYSCTL_SETTING_KEY = "sysctl"


# Copied from pkgpanda/actions.py#L308-L327
def _apply_sysctl(setting, service):
    try:
        subprocess.check_call(["sysctl", "-q", "-w", setting])
    except subprocess.CalledProcessError:
        log.warning("sysctl {setting} not set for {service}".format(setting=setting, service=service))


def _apply_sysctl_settings(sysctl_settings, service):
    for setting, value in sysctl_settings.get(service, {}).items():
        _apply_sysctl("{setting}={value}".format(setting=setting, value=value), service)


def apply_service_configuration(service):
    if not os.path.exists(DCOS_SERVICE_CONFIGURATION_PATH):
        return

    dcos_service_properties = load_json(DCOS_SERVICE_CONFIGURATION_PATH)
    if SYSCTL_SETTING_KEY in dcos_service_properties:
        _apply_sysctl_settings(dcos_service_properties[SYSCTL_SETTING_KEY], service)
