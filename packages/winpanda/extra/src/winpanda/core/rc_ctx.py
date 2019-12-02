"""Panda package management for Windows.

Resource rendering context calculation stuff.
"""
import configparser as cfp
import json

from common import constants as cm_const
from common import logger
from common.storage import ISTOR_NODE, IStorNodes
from core.package.id import PackageId


LOG = logger.get_logger(__name__)


class RCCONTEXT_ITEM:
    """Element of resource rendering context."""
    MASTER_PRIV_IPADDR = 'master_priv_ipaddr'
    LOCAL_PRIV_IPADDR = 'local_priv_ipaddr'
    ZK_CLIENT_PORT = 'zk_client_port'

    DCOS_INST_DPATH = 'dcos_inst_dpath'
    DCOS_CFG_DPATH = 'dcos_cfg_dpath'
    DCOS_WORK_DPATH = 'dcos_work_dpath'
    DCOS_RUN_DPATH = 'dcos_run_dpath'
    DCOS_LOG_DPATH = 'dcos_log_dpath'
    DCOS_TMP_DPATH = 'dcos_tmp_dpath'
    DCOS_BIN_DPATH = 'dcos_bin_dpath'
    DCOS_LIB_DPATH = 'dcos_lib_dpath'

    PKG_INST_DPATH = 'pkg_inst_dpath'
    PKG_LOG_DPATH = 'pkg_log_dpath'
    PKG_RTD_DPATH = 'pkg_rtd_dpath'
    PKG_WORK_DPATH = 'pkg_work_dpath'
    PKG_SHRCFG_DPATH = 'pkg_shrcfg_dpath'


class ResourceContext:
    """Resource rendering context manager."""
    def __init__(self, istor_nodes=None, cluster_conf=None, pkg_id=None):
        """Constructor.

        :param istor_nodes:  IStorNodes, DC/OS installation storage nodes (set
                             of pathlib.Path objects)
        :param cluster_conf: dict, configparser.ConfigParser.read_dict()
                             compatible data. DC/OS cluster setup parameters
        :param pkg_id:       PackageId, package ID
        """
        if istor_nodes is not None:
            assert isinstance(istor_nodes, IStorNodes), (
                f'Argument: istor_nodes:'
                f' Got {type(istor_nodes).__name__} instead of IStorNodes'
            )
        if cluster_conf is not None:
            assert isinstance(cluster_conf, dict), (
                f'Argument: cluster_conf:'
                f'Got {type(cluster_conf).__name__} instead of dict'
            )
        if pkg_id is not None:
            assert isinstance(pkg_id, PackageId), (
                f'Argument: pkg_id: PackageId is required: {pkg_id}'
            )

        self._istor_nodes = istor_nodes
        self._cluster_conf = cluster_conf
        self._pkg_id = pkg_id

    def get_items(self, json_ready=False):
        """Get resource rendering context items.

        :param json_ready: bool, get JSON-compatible context items, if True
        :return:           dict, set of resource rendering context items
        """
        retrievers = (self._get_istor_items,
                      self._get_cluster_conf_items,
                      self._get_pkg_items)
        items = {}

        for retriever in retrievers:
            items.update(retriever(json_ready))

        return items

    def _get_istor_items(self, json_ready=False):
        """Discover resource rendering context items from DC/OS installation
        storage configuration.

        :param json_ready: bool, get JSON-compatible context items, if True
        :return:           dict, set of resource rendering context items
        """
        if self._istor_nodes is None:
            return {}

        items = {
            RCCONTEXT_ITEM.DCOS_INST_DPATH: json.dumps(str(
                getattr(self._istor_nodes, ISTOR_NODE.ROOT)
            )).strip('"') if json_ready else str(
                getattr(self._istor_nodes, ISTOR_NODE.ROOT)
            ),
            RCCONTEXT_ITEM.DCOS_CFG_DPATH: json.dumps(str(
                getattr(self._istor_nodes, ISTOR_NODE.CFG)
            )).strip('"') if json_ready else str(
                getattr(self._istor_nodes, ISTOR_NODE.CFG)
            ),
            RCCONTEXT_ITEM.DCOS_WORK_DPATH: json.dumps(str(
                getattr(self._istor_nodes, ISTOR_NODE.WORK)
            )).strip('"') if json_ready else str(
                getattr(self._istor_nodes, ISTOR_NODE.WORK)
            ),
            RCCONTEXT_ITEM.DCOS_RUN_DPATH: json.dumps(str(
                getattr(self._istor_nodes, ISTOR_NODE.RUN)
            )).strip('"') if json_ready else str(
                getattr(self._istor_nodes, ISTOR_NODE.RUN)
            ),
            RCCONTEXT_ITEM.DCOS_LOG_DPATH: json.dumps(str(
                getattr(self._istor_nodes, ISTOR_NODE.LOG)
            )).strip('"') if json_ready else str(
                getattr(self._istor_nodes, ISTOR_NODE.LOG)
            ),
            RCCONTEXT_ITEM.DCOS_TMP_DPATH: json.dumps(str(
                getattr(self._istor_nodes, ISTOR_NODE.TMP)
            )).strip('"') if json_ready else str(
                getattr(self._istor_nodes, ISTOR_NODE.TMP)
            ),
            RCCONTEXT_ITEM.DCOS_BIN_DPATH: json.dumps(str(
                getattr(self._istor_nodes, ISTOR_NODE.BIN)
            )).strip('"') if json_ready else str(
                getattr(self._istor_nodes, ISTOR_NODE.BIN)
            ),
            RCCONTEXT_ITEM.DCOS_LIB_DPATH: json.dumps(str(
                getattr(self._istor_nodes, ISTOR_NODE.LIB)
            )).strip('"') if json_ready else str(
                getattr(self._istor_nodes, ISTOR_NODE.LIB)
            ),
        }

        return items

    def _get_cluster_conf_items(self, json_ready=False):
        """Extract resource rendering context items from cluster configuration.

        :param json_ready: bool, get JSON-compatible context items, if True
        :return:           dict, set of resource rendering context items
        """
        if self._cluster_conf is None:
            return {}

        cluster_conf = cfp.ConfigParser()
        cluster_conf.read_dict(self._cluster_conf)

        mnode_cfg_items = [
            (cluster_conf.get(s, 'privateipaddr',
                              fallback='127.0.0.1'),
             cluster_conf.get(s, 'zookeeperclientport',
                              fallback=cm_const.ZK_CLIENTPORT_DFT))
            for s in cluster_conf.sections() if s.startswith('master-node')
        ]
        master_priv_ipaddr = mnode_cfg_items[0][0] if mnode_cfg_items else (
            '127.0.0.1'
        )
        zk_client_port = mnode_cfg_items[0][1] if mnode_cfg_items else (
            cm_const.ZK_CLIENTPORT_DFT
        )
        local_priv_ipaddr = cluster_conf.get(
            'local', 'privateipaddr', fallback='127.0.0.1'
        )

        items = {
            RCCONTEXT_ITEM.MASTER_PRIV_IPADDR: master_priv_ipaddr,
            RCCONTEXT_ITEM.LOCAL_PRIV_IPADDR: local_priv_ipaddr,
            RCCONTEXT_ITEM.ZK_CLIENT_PORT: zk_client_port
        }

        return items

    def _get_pkg_items(self, json_ready=False):
        """Calculate resource rendering context items specific to a particular
        DC/OS package.

        :param json_ready: bool, get JSON-compatible context items, if True
        :return:           dict, set of resource rendering context items
        """
        if self._istor_nodes is None or self._pkg_id is None:
            return {}

        pkg_inst_dpath = (
            getattr(self._istor_nodes, ISTOR_NODE.PKGREPO).joinpath(
                self._pkg_id.pkg_id
            )
        )
        pkg_log_dpath = getattr(self._istor_nodes, ISTOR_NODE.LOG).joinpath(
            self._pkg_id.pkg_name
        )
        pkg_rtd_dpath = getattr(self._istor_nodes, ISTOR_NODE.RUN).joinpath(
            self._pkg_id.pkg_name
        )
        pkg_work_dpath = getattr(self._istor_nodes, ISTOR_NODE.WORK).joinpath(
            self._pkg_id.pkg_name
        )
        pkg_shrcfg_dpath = getattr(self._istor_nodes, ISTOR_NODE.CFG).joinpath(
            self._pkg_id.pkg_name
        )

        items = {
            RCCONTEXT_ITEM.PKG_INST_DPATH: json.dumps(str(
                pkg_inst_dpath
            )).strip('"') if json_ready else str(pkg_inst_dpath),

            RCCONTEXT_ITEM.PKG_LOG_DPATH: json.dumps(str(
                pkg_log_dpath
            )).strip('"') if json_ready else str(pkg_log_dpath),

            RCCONTEXT_ITEM.PKG_RTD_DPATH: json.dumps(str(
                pkg_rtd_dpath
            )).strip('"') if json_ready else str(pkg_rtd_dpath),

            RCCONTEXT_ITEM.PKG_WORK_DPATH: json.dumps(str(
                pkg_work_dpath
            )).strip('"') if json_ready else str(pkg_work_dpath),

            RCCONTEXT_ITEM.PKG_SHRCFG_DPATH: json.dumps(str(
                pkg_shrcfg_dpath
            )).strip('"') if json_ready else str(pkg_shrcfg_dpath),
        }

        return items

    def as_dict(self):
        """Construct the dict representation."""
        if self._istor_nodes is None:
            istor_nodes = None
        else:
            istor_nodes = {
                k: str(v) for k, v in self._istor_nodes._asdict().items()
            }

        return {
            'istor_nodes': istor_nodes,
            'cluster_conf': self._cluster_conf,
            'pkg_id': self._pkg_id.pkg_id,
        }
