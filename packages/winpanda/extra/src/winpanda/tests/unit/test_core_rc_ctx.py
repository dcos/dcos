import unittest
import mock

from common.storage import ISTOR_NODE
from core.rc_ctx import ResourceContext, RCCONTEXT_ITEM

STUB_ISTORE_NODES_CONFIG = {
    ISTOR_NODE.ROOT: 'val_root',
    ISTOR_NODE.TMP: 'val_tmp',
    ISTOR_NODE.BIN: 'val_bin',
    ISTOR_NODE.LIB: 'val_lib',
    ISTOR_NODE.CFG: mock.Mock(),
    ISTOR_NODE.WORK: mock.Mock(),
    ISTOR_NODE.RUN: mock.Mock(),
    ISTOR_NODE.LOG: mock.Mock(),
    ISTOR_NODE.PKGREPO: mock.Mock()
}

RCCONTEXT_ITEMS = [
    RCCONTEXT_ITEM.DCOS_INST_DPATH,
    RCCONTEXT_ITEM.DCOS_CFG_DPATH,
    RCCONTEXT_ITEM.DCOS_WORK_DPATH,
    RCCONTEXT_ITEM.DCOS_RUN_DPATH,
    RCCONTEXT_ITEM.DCOS_LOG_DPATH,
    RCCONTEXT_ITEM.DCOS_TMP_DPATH,
    RCCONTEXT_ITEM.DCOS_BIN_DPATH,
    RCCONTEXT_ITEM.DCOS_LIB_DPATH,
    RCCONTEXT_ITEM.PKG_INST_DPATH,
    RCCONTEXT_ITEM.PKG_LOG_DPATH,
    RCCONTEXT_ITEM.PKG_RTD_DPATH,
    RCCONTEXT_ITEM.PKG_WORK_DPATH,
    RCCONTEXT_ITEM.PKG_SHRCFG_DPATH
]


class TestPackageId(unittest.TestCase):
    @staticmethod
    def get_nodes():
        return type("Foo", (object,), STUB_ISTORE_NODES_CONFIG)()

    def test_default_get_items_should_be_empty(self):
        context = ResourceContext()

        assert context.get_items() == {}

    def test_cluster_conf_items_should_correspond_stub(self):
        context = ResourceContext(istor_nodes=self.get_nodes())
        items = context.get_items()

        assert items[RCCONTEXT_ITEM.DCOS_INST_DPATH] == 'val_root'
        assert items[RCCONTEXT_ITEM.DCOS_TMP_DPATH] == 'val_tmp'
        assert items[RCCONTEXT_ITEM.DCOS_BIN_DPATH] == 'val_bin'
        assert items[RCCONTEXT_ITEM.DCOS_LIB_DPATH] == 'val_lib'

    def test_cluster_items_should_be_not_empty(self):
        context = ResourceContext(cluster_conf={}, extra_values={'privateipaddr': '192.168.1.1'})
        itms = context.get_items()

        assert itms == {
            RCCONTEXT_ITEM.MASTER_LOCATION: '127.0.0.1:2181',
            RCCONTEXT_ITEM.MASTER_PRIV_IPADDR: '127.0.0.1',
            RCCONTEXT_ITEM.LOCAL_PRIV_IPADDR: '192.168.1.1',
            RCCONTEXT_ITEM.ZK_CLIENT_PORT: 2181,
            'privateipaddr': '192.168.1.1'
        }

    def test_pkg_items_should_provide_all_keys(self):
        pkg_id = mock.Mock()
        context = ResourceContext(istor_nodes=self.get_nodes(), pkg_id=pkg_id)
        items = context.get_items()
        assert list(items.keys()) == RCCONTEXT_ITEMS

    def test_extra_items_should_provide_all_keys(self):
        context = ResourceContext(extra_values={'key': 'val'})
        items = context.get_items()

        assert items['key'] == 'val'

    def test_clusters_items_should_provide_correct_location(self):
        context = ResourceContext(cluster_conf={
            'master-node-1': {'privateipaddr': '192.168.1.1', 'zookeeperlistenerport': '2181'},
            'master-node-2': {'privateipaddr': '192.168.1.2', 'zookeeperlistenerport': '2182'},
        }, extra_values={'privateipaddr': '192.168.1.1'})
        items = context.get_items()

        assert items[RCCONTEXT_ITEM.MASTER_LOCATION] == '192.168.1.1:2181,192.168.1.2:2181'

    def test_discovery_type_static_should_provide_correct_location(self):
        context = ResourceContext(cluster_conf={
            'master-node-1': {'privateipaddr': '192.168.1.1', 'zookeeperlistenerport': '2181'},
            'master-node-2': {'privateipaddr': '192.168.1.2', 'zookeeperlistenerport': '2182'},
            'discovery': {'type': 'static'}
        }, extra_values={'privateipaddr': '192.168.1.1'})
        items = context.get_items()

        assert items[RCCONTEXT_ITEM.MASTER_LOCATION] == '192.168.1.1:2181'
