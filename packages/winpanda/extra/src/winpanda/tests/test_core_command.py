import pytest

from common import storage
from core import command, cmdconf


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

# TODO: Indentation is not preserved. This will be fixed during change
# to pkgpanda templating.

FILE1_CONTENTS = r'''word
red
aws
"true"'''

# Files ending in .json do not have replacement values escaped.
FILE2_CONTENTS = r'''{
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
    assert file1_path.read_text() == FILE1_CONTENTS
    assert file2_path.read_text() == FILE2_CONTENTS


# TODO: Making Jinja2 fail here is non-trivial, but we can fix this as
# part of change to pkgpanda templating
@pytest.mark.skip("should fail, but doesn't")
def test_dcos_config_missing_variable(tmp_path):
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
    setup._deploy_dcos_conf()

    file1_path = root_path / 'file1.txt'
    file2_path = root_path / 'subdir' / 'file2'

    assert not file1_path.exists()
    assert not file2_path.exists()
