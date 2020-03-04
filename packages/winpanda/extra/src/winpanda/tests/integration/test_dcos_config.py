import pytest

from common import storage
from core import command, cmdconf, template as tmpl


_DCOS_CONFIG = r'''
package:
  - path: {{ windows_dcos_install_path }}\file1.txt
    content: |
      word
      {{ color }}
          {{ provider }}
      {{ escaped }}
  - path: {{ windows_dcos_install_path }}\subdir\file2.json
    content: |
        {
            value: {{ escaped }}
        }

'''

_FILE1_CONTENTS = r'''word
red
    aws
"true"
'''

# Files ending in .json are treated the same as other files, with no special escaping.
_FILE2_CONTENTS = r'''{
    value: "true"
}
'''


@cmdconf.cmdconf_type('test')
class SetupConf:

    def __init__(self, **cmd_opts):
        self._opts = cmd_opts

    def __getattr__(self, name):
        return self._opts[name]


def test_dcos_config_ok(tmp_path):
    """
    Files are templated and indented according to YAML.
    """
    root_path = tmp_path / 'root'
    values = {
        'windows_dcos_install_path': str(root_path),
        'color': 'red',
        'provider': 'aws',
        'escaped': '"true"',
    }
    dcos_config_path = tmp_path / 'dcos-config-windows.yaml'
    dcos_config_path.write_text(_DCOS_CONFIG)

    template = cmdconf.CmdConfigSetup.load_dcos_conf_template(dcos_config_path)
    dcos_conf = {'template': template, 'values': values}

    inst_storage = storage.InstallationStorage(
        root_dpath=str(tmp_path / 'root')
    )

    cluster_conf = None

    setup = command.CmdSetup(
        command_name='test',
        dcos_conf=dcos_conf,
        cluster_conf=cluster_conf,
        inst_storage=inst_storage,
    )
    setup._deploy_dcos_conf()

    file1_path = root_path / 'file1.txt'
    file2_path = root_path / 'subdir' / 'file2.json'

    assert file1_path.exists()
    assert file2_path.exists()
    assert file1_path.read_text() == _FILE1_CONTENTS
    assert file2_path.read_text() == _FILE2_CONTENTS


_DCOS_CONFIG_SWITCH = r'''
package:
{% switch provider %}
{% case "aws" %}
  - path: {{ windows_dcos_install_path }}\file1.txt
    permissions: "0600"
    content: {{ color }}
{% case "azure" %}
{% endswitch %}
  - path: {{ windows_dcos_install_path }}\file2.txt
    content: |
{% switch provider %}
{% case "aws" %}
        1
{% case "azure" %}
        2
{% endswitch %}
        {{ escaped }}
'''

_FILE2_CONTENTS_AWS = r'''
1

"true"
'''

_FILE2_CONTENTS_AZURE = r'''
2

"true"
'''


def test_dcos_config_aws(tmp_path):
    """
    First replacement is used.
    """
    root_path = tmp_path / 'root'
    values = {
        'windows_dcos_install_path': str(root_path),
        'color': 'red',
        'provider': 'aws',
        'escaped': '"true"',
    }
    dcos_config_path = tmp_path / 'dcos-config-windows.yaml'
    dcos_config_path.write_text(_DCOS_CONFIG_SWITCH)

    template = cmdconf.CmdConfigSetup.load_dcos_conf_template(dcos_config_path)
    dcos_conf = {'template': template, 'values': values}

    inst_storage = storage.InstallationStorage(
        root_dpath=str(tmp_path / 'root')
    )

    cluster_conf = None

    setup = command.CmdSetup(
        command_name='test',
        dcos_conf=dcos_conf,
        cluster_conf=cluster_conf,
        inst_storage=inst_storage,
    )
    setup._deploy_dcos_conf()

    file1_path = root_path / 'file1.txt'
    file2_path = root_path / 'file2.txt'

    assert file1_path.exists()
    assert file2_path.exists()
    assert file1_path.read_text() == 'red'
    assert file2_path.read_text() == _FILE2_CONTENTS_AWS


def test_dcos_config_azure(tmp_path):
    """
    Second replacement is used.
    """
    root_path = tmp_path / 'root'
    values = {
        'windows_dcos_install_path': str(root_path),
        'color': 'red',
        'provider': 'azure',
        'escaped': '"true"',
    }
    dcos_config_path = tmp_path / 'dcos-config-windows.yaml'
    dcos_config_path.write_text(_DCOS_CONFIG_SWITCH)

    template = cmdconf.CmdConfigSetup.load_dcos_conf_template(dcos_config_path)
    dcos_conf = {'template': template, 'values': values}

    inst_storage = storage.InstallationStorage(
        root_dpath=str(tmp_path / 'root')
    )

    cluster_conf = None

    setup = command.CmdSetup(
        command_name='test',
        dcos_conf=dcos_conf,
        cluster_conf=cluster_conf,
        inst_storage=inst_storage,
    )
    setup._deploy_dcos_conf()

    file1_path = root_path / 'file1.txt'
    file2_path = root_path / 'file2.txt'

    assert not file1_path.exists()
    assert file2_path.exists()
    assert file2_path.read_text() == _FILE2_CONTENTS_AZURE


def test_dcos_config_missing_variable(tmp_path):
    """
    Templating fails if a parameter is not set.
    """
    root_path = tmp_path / 'root'
    values = {
        'windows_dcos_install_path': str(root_path),
        'provider': 'aws',
    }
    dcos_config_path = tmp_path / 'dcos-config-windows.yaml'
    dcos_config_path.write_text(_DCOS_CONFIG)

    template = cmdconf.CmdConfigSetup.load_dcos_conf_template(dcos_config_path)
    dcos_conf = {'template': template, 'values': values}

    inst_storage = storage.InstallationStorage(
        root_dpath=str(tmp_path / 'root')
    )

    cluster_conf = None

    setup = command.CmdSetup(
        command_name='test',
        dcos_conf=dcos_conf,
        cluster_conf=cluster_conf,
        inst_storage=inst_storage,
    )
    with pytest.raises(tmpl.UnsetParameter):
        setup._deploy_dcos_conf()
