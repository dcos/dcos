import mock

from common.cli import CLI_CMDOPT
from pathlib import Path
from core.cmdconf import get_cluster_conf


def test_get_cluster_conf():
    path = mock.Mock(spec=Path)
    content = {
        'DEFAULT': {},
        'master-node-1': {'privateipaddr': '192.168.1.1', 'zookeeperlistenerport': '2181'},
        'distribution-storage': {
            'rooturl': 'http://172.168.1.2:8080/2.1.0-beta1/genconf/serve',
            'pkgrepopath': 'windows/packages',
            'pkglistpath': 'windows/package_lists/latest.package_list.json',
            'dcosclusterpkginfopath': 'cluster-package-info.json'
        },
        'local': {
            'privateipaddr': '192.168.0.254'
        }
    }

    with mock.patch("core.cmdconf.cr_utl.rc_load_ini", return_value=content):
        result = get_cluster_conf(path, **{
            CLI_CMDOPT.DCOS_CLUSTERCFGPATH: 'test'
        })

    assert content == result
