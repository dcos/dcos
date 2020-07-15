import json
import logging
import os
import shutil
import socket
import stat
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

install_path = Path('/opt/mesosphere')
dcos_lib_path = Path('/var/lib/dcos')
dcos_run_path = Path('/run/dcos')
tmp_path = Path('/tmp')

dcos_etc_path = install_path / 'etc'


# Derived from pkgpanda/util.py#L257-L262
def load_json(filepath):
    try:
        with filepath.open() as f:
            return json.load(f)
    except ValueError as ex:
        raise ValueError("Invalid JSON in {0}: {1}".format(filepath, ex)) from ex


def read_file_text(filepath):
    with filepath.open() as f:
        return f.read().strip()


def read_file_bytes(filepath):
    with filepath.open('rb') as f:
        return f.read()


def write_readonly_file(filepath, data):
    _write_file_bytes(filepath, data, 0o400)


def write_private_file(filepath, data):
    _write_file_bytes(filepath, data, 0o600)


def write_public_file(filepath, data):
    _write_file_bytes(filepath, data, 0o644)


def _write_file_bytes(filepath, data, mode):
    """
    Set the contents of file to a byte string.

    The code ensures an atomic write by creating a temporary file and then
    moving that temporary file to the given ``filename``. This prevents race
    conditions such as the file being read by another process after it is
    created but not yet written to.

    It also prevents an invalid file being created if the `write` fails (e.g.
    because of low disk space).

    On Linux the new file is created with permissions `mode`.

    This function does not attempt to fsync the file to disk. fsync protects
    files being lost following an OS crash. However, the bootstrap process is
    always re-run before services restart. Hence, any files not persisted to
    disk will be recreated after a crash.
    """
    filename = str(filepath)
    prefix = os.path.basename(filename)
    tmp_file_dir = os.path.dirname(os.path.realpath(filename))
    fd, temporary_filename = tempfile.mkstemp(prefix=prefix, dir=tmp_file_dir)
    # On Linux `mkstemp` initially creates file with permissions 0o600
    try:
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        os.chmod(temporary_filename, stat.S_IMODE(mode))
        os.replace(temporary_filename, filename)
    except Exception:
        os.remove(temporary_filename)
        raise


def write_file_on_mismatched_content(desired_content, target, write):
    """
    Write the contents to a new target.

    The copy is atomic, ensuring that the target file never exists with
    partial contents.  The code avoids writing the file if the contents
    do not need to be updated.  The return value is a boolean indicating
    whether the contents of the file changed.
    """
    if target.exists():
        current_content = read_file_bytes(target)
        if current_content == desired_content:
            return False

    write(target, desired_content)
    return True


def chown(path, user=None, group=None):
    shutil.chown(str(path), user, group)


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
    cmd = [str(install_path / 'bin' / 'detect_ip')]
    machine_ip = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('ascii').strip()
    validate_ipv4_addresses([machine_ip])
    return machine_ip


DCOS_SERVICE_CONFIGURATION_FILE = "dcos-service-configuration.json"
DCOS_SERVICE_CONFIGURATION_PATH = dcos_etc_path / DCOS_SERVICE_CONFIGURATION_FILE
SYSCTL_SETTING_KEY = "sysctl"


# Derived from pkgpanda/actions.py#L308-L327
def _apply_sysctl(setting, service):
    try:
        subprocess.check_call(["sysctl", "-q", "-w", setting])
    except subprocess.CalledProcessError:
        log.warning("sysctl {setting} not set for {service}".format(setting=setting, service=service))


def _apply_sysctl_settings(sysctl_settings, service):
    for setting, value in sysctl_settings.get(service, {}).items():
        _apply_sysctl("{setting}={value}".format(setting=setting, value=value), service)


def apply_service_configuration(service):
    if DCOS_SERVICE_CONFIGURATION_PATH.exists():
        dcos_service_properties = load_json(DCOS_SERVICE_CONFIGURATION_PATH)
        if SYSCTL_SETTING_KEY in dcos_service_properties:
            _apply_sysctl_settings(dcos_service_properties[SYSCTL_SETTING_KEY], service)
