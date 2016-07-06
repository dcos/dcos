import logging
import os

CONFIG_PATH = '/genconf/config.yaml'
SSH_KEY_PATH = '/genconf/ssh_key'
IP_DETECT_PATH = '/genconf/ip-detect'
REXRAY_CONFIG_PATH = '/genconf/rexray.yaml'
SERVE_DIR = '/genconf/serve'
STATE_DIR = '/genconf/state'
GENCONF_DIR = '/genconf'

log = logging.getLogger(__name__)


def write_file(data, path):
    try:
        with open(path, 'w') as f:
            log.debug("Writing file %s", path)
            f.write(data)
    except:
        log.error("Filed to write path %s", path)


def get_action_state(action_name):
    """
    Check the action.json file and if the
    success + failed + term == total then we are finished.
    If not, return running.
    """
    return {
        "action_name": "deploy",
        "action_state": "running",
        "hosts_running": [],
        "hosts_success": [],
        "hosts_failed": [],
        "hosts_terminated": [],
    }


def clear_action_jsons():
    """
    On startup, remove all the old action.json files (preflight,
    postflight, deploy .json). This is because action state is
    nullified when the installer shuts down. This way we do not
    return inconsistent state in the get_action_state().
    """
    pass


def create_directory(path):
    if not os.path.exists(path):
        os.mkdirs(path)
