"""
Configuration loader for dcosgen
Set all configuration for a given run with a simple map
my_opts = {
    'config_dir':  '/tmp'
}

c = DcosConfig()
print(c)
"""
import json
import logging
import os
import yaml

from dcos_installer.constants import CONFIG_PATH, SSH_KEY_PATH, IP_DETECT_PATH
log = logging.getLogger(__name__)


def stringify_configuration(configuration):
    """Create a stringified version of the complete installer configuration
    to send to gen.generate()"""
    gen_config = {}
    for key, value in configuration.items():
        if isinstance(value, list) or isinstance(value, dict):
            log.debug("Caught %s for genconf configuration, transforming to JSON string: %s", type(value), value)
            value = json.dumps(value)

        elif isinstance(value, bool):
            if value:
                value = 'true'
            else:
                value = 'false'

        elif isinstance(value, int):
            log.debug("Caught int for genconf configuration, transforming to string: %s", value)
            value = str(value)

        elif isinstance(value, str):
            pass

        else:
            log.error("Invalid type for value of %s in config. Got %s, only can handle list, dict, "
                      "int, bool, and str", key, type(value))
            raise Exception()

        gen_config[key] = value

    log.debug('Stringified configuration: \n{}'.format(gen_config))
    return gen_config


class DCOSConfig(dict):
    """
    Return the site configuration object for dcosgen library
    """
    def __init__(self, overrides={}, config_path=CONFIG_PATH, write_default_config=True):
        defaults = """
---
# The name of your DC/OS cluster. Visable in the DC/OS user interface.
cluster_name: 'DC/OS'
master_discovery: static
exhibitor_storage_backend: 'static'
resolvers:
- 8.8.8.8
- 8.8.4.4
ssh_port: 22
process_timeout: 10000
bootstrap_url: file:///opt/dcos_install_tmp
"""
        self.write_default_config = write_default_config
        self.defaults = yaml.load(defaults)
        self.config_path = config_path
        self.overrides = overrides
        self._build()

        log.debug("Configuration:")
        for k, v in self.items():
            log.debug("%s: %s", k, v)

    def get_hidden_config(self):
        self.hidden_config = {
            'ip_detect_filename':  IP_DETECT_PATH,
            'ssh_key_path': SSH_KEY_PATH,
        }

    def get_external_config(self):
        self.external_config = {
            'ssh_key': self._try_loading_from_disk(SSH_KEY_PATH),
            'ip_detect_script': self._try_loading_from_disk(IP_DETECT_PATH)
        }

    def _try_loading_from_disk(self, path):
        if os.path.isfile(path):
            with open(path, 'r') as f:
                return f.read()
        else:
            return None

    def _build(self):
        """Build takes the default configuration, overrides this with
        the config on disk, and overrides that with configruation POSTed
        to the backend"""
        # Create defaults
        for key, value in self.defaults.items():
            self[key] = value

        # Add user-land configuration
        user_config = self.get_config_from_disk()
        if user_config:
            for k, v in user_config.items():
                self[k] = v

        # Override with POST data
        self._add_overrides()

    def _add_overrides(self):
        if self.overrides is not None and len(self.overrides) > 0:
            for key, value in self.overrides.items():
                if value is None:
                    log.warning("Adding new configuration %s: %s", key, value)
                    self[key] = value

                elif key in self:
                    log.warning("Overriding %s: %s -> %s", key, self[key], value)
                    self[key] = value

                else:
                    log.warning("Adding new value %s: %s", key, value)
                    self[key] = value

    def get_config_from_disk(self):
        if os.path.isfile(self.config_path):
            log.debug("Loading YAML configuration: %s", self.config_path)
            with open(self.config_path, 'r') as data:
                configuration = yaml.load(data)

        else:
            if self.write_default_config:
                log.error(
                    "Configuration file not found, %s. Writing new one with all defaults.",
                    self.config_path)
                self.write()
                configuration = yaml.load(open(self.config_path))
            else:
                log.error("Configuration file not found: %s", self.config_path)
                return {}

        return configuration

    def write(self):
        """Write the configuration to disk, removing keys that are not permitted to be
        used by end-users"""
        if self.config_path:
            self._remove_unrequired_config_keys()
            data = open(self.config_path, 'w')
            data.write(yaml.dump(self._unbind_configuration(), default_flow_style=False, explicit_start=True))
            data.close()
        else:
            log.error("Must pass config_path=/path/to/file to execute .write().")

    def print_to_screen(self):
        print(yaml.dump(self._unbind_configuration(), default_flow_style=False, explicit_start=True))

    def _unbind_configuration(self):
        """Unbinds the methods and class variables from the DCOSConfig
        object and returns a simple dictionary.
        """
        dictionary = {}
        for k, v in self.items():
            dictionary[k] = v

        return dictionary

    def stringify_configuration(self):
        """Create a stringified version of the complete installer configuration
        to send to gen.generate()"""
        return stringify_configuration(self)

    def _remove_unrequired_config_keys(self):
        """Remove the configuration we do not want
        in the config file.

        :param config: The config dictionary
        :type config: dict | {}
        """
        do_not_write = [
            'ssh_key',
            'ssh_key_path',
            'ip_detect_path',
            'ip_detect_script'
        ]
        for key in do_not_write:
            if key in self:
                del self[key]
