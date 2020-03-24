import mock
import unittest
import pytest
import os
import yaml

from common.cli import CLI_CMDOPT
from pathlib import Path
from core.cmdconf import get_cluster_conf, CmdConfigSetup, load_dcos_conf_template
from core import utils
from common.exceptions import WinpandaError


class TestCmdConfigSetup(unittest.TestCase):
    @staticmethod
    def stubs_location():
        location = os.path.abspath(__file__)
        return os.path.join(os.path.dirname(location), '..', 'data')

    @classmethod
    def mock_get_dcos_conf(cls):
        template_fpath = Path(cls.stubs_location()).joinpath('dcos-config-windows.yaml')
        template = load_dcos_conf_template(template_fpath)
        values = utils.rc_load_json(
            Path(cls.stubs_location()).joinpath('expanded.config.full.json'),
            emheading=f'DC/OS aggregated config: Values'
        )
        return {'template': template, 'values': values}

    @property
    def cmd_config_opts(self):
        return {
            CLI_CMDOPT.DCOS_CLUSTERCFGPATH: os.path.join(self.stubs_location(), 'cluster_conf.ini'),
            CLI_CMDOPT.INST_ROOT: self.stubs_location(),
            CLI_CMDOPT.INST_CONF: 'fake_cfg_path',
            CLI_CMDOPT.INST_PKGREPO: 'fake_repo_path',
            CLI_CMDOPT.INST_STATE: 'fake_inst_state',
            CLI_CMDOPT.INST_VAR: 'data'
        }

    @mock.patch.object(CmdConfigSetup, 'get_ref_pkg_list', return_value={})
    @mock.patch.object(CmdConfigSetup, 'get_dcos_conf')
    def test_dcos_conf_should_contain_package(self, mock_get_dcos_conf, *args):
        mock_get_dcos_conf.return_value = self.mock_get_dcos_conf()

        cfg = CmdConfigSetup(**self.cmd_config_opts)

        template = cfg.dcos_conf.get('template')
        values = cfg.dcos_conf.get('values')
        rendered = template.render(values)

        config = yaml.safe_load(rendered)

        assert config.keys() == {"package"}

    @mock.patch.object(CmdConfigSetup, 'get_ref_pkg_list', return_value={})
    @mock.patch.object(CmdConfigSetup, 'get_dcos_conf')
    def test_cluster_conf_should_require_dstor_url(self, mock_get_dcos_conf, *args):
        mock_get_dcos_conf.return_value = self.mock_get_dcos_conf()
        cfg = CmdConfigSetup(**self.cmd_config_opts)

        with pytest.raises(WinpandaError):
            cfg.get_cluster_conf()

    @mock.patch.object(CmdConfigSetup, 'get_ref_pkg_list', return_value={})
    @mock.patch.object(CmdConfigSetup, 'get_dcos_conf')
    def test_cluster_conf_should_require_local_priv_ipaddr(self, mock_get_dcos_conf, *args):
        mock_get_dcos_conf.return_value = self.mock_get_dcos_conf()

        opts = self.cmd_config_opts
        opts[CLI_CMDOPT.DSTOR_URL] = 'http://172.16.2.187:8080/2.1.0-beta1/genconf/serve'

        cfg = CmdConfigSetup(**opts)

        with pytest.raises(WinpandaError):
            cfg.get_cluster_conf()

    @mock.patch.object(CmdConfigSetup, 'get_ref_pkg_list', return_value={})
    @mock.patch.object(CmdConfigSetup, 'get_dcos_conf')
    def test_cluster_conf_should_contain_keys(self, mock_get_dcos_conf, *args):
        mock_get_dcos_conf.return_value = self.mock_get_dcos_conf()

        opts = self.cmd_config_opts
        opts[CLI_CMDOPT.DSTOR_URL] = 'http://172.16.2.187:8080/2.1.0-beta1/genconf/serve'
        opts[CLI_CMDOPT.LOCAL_PRIVIPADDR] = '172.16.27.209'

        cfg = CmdConfigSetup(**opts)
        cluster_cfg = cfg.get_cluster_conf()

        assert "local" in cluster_cfg.keys()
        assert "distribution-storage" in cluster_cfg.keys()
        assert "discovery" in cluster_cfg.keys()
