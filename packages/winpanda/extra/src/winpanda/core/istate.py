"""Panda package management for Windows.

DC/OS installation state descriptor type definition.
"""
import json
from pathlib import Path

from common import logger
from common import constants as cm_const
from common.storage import ISTOR_NODE, IStorNodes
from core import exceptions as cr_exc
from core import utils as cr_utl


LOG = logger.get_logger(__name__)


class ISTATE:
    """DC/OS installation states codes."""
    UNDEFINED = 'UNDEFINED'
    INSTALLATION_IN_PROGRESS = 'INSTALLATION_IN_PROGRESS'
    INSTALLATION_FAILED = 'INSTALLATION_FAILED'
    INSTALLED = 'INSTALLED'
    UPGRADE_IN_PROGRESS = 'UPGRADE_IN_PROGRESS'
    UPGRADE_FAILED = 'UPGRADE_FAILED'


VALID_ISTATES = [
    getattr(ISTATE, i) for i in ISTATE.__dict__ if not i.startswith('__')
]


class InstallationState:
    """DC/OS installation state descriptor."""
    def __init__(self, istor_nodes: IStorNodes=None,
                 istate: str=ISTATE.UNDEFINED, istate_dpath: Path=None,
                 save: bool=True):
        """Constructor.

        :param istor_nodes:  IStorNodes, DC/OS installation storage nodes (set
                             of pathlib.Path objects)
        :param istate:       str, DC/OS installation state code
        :param istate_dpath: Path, absolute path to the DC/OS state
                             directory within the local DC/OS installation
                             storage
        :param save:         bool, save DC/OS installation state descriptor to
                             file, if True
        """
        self.msg_src = self.__class__.__name__

        if istor_nodes is not None:
            istate_dpath = getattr(istor_nodes, ISTOR_NODE.STATE)
        elif istate_dpath is None:
            assert False, (
                f'{self.msg_src}: Argument: Either istor_nodes or istate_dpath'
                f'must be specified'
            )
        assert istate in VALID_ISTATES, (
            f'{self.msg_src}: Argument: istate: Invalid value: {istate}'
        )

        self._istor_nodes = istor_nodes
        self._istate = istate
        self._istate_dpath = istate_dpath

        if save is True:
            self.save()

    def __str__(self):
        return str(self.body)

    def __eq__(self, other):
        if not isinstance(other, InstallationState):
            return False

        return (self._istor_nodes == other._istor_nodes and
                self._istate == other._istate and
                self._istate_dpath == other._istate_dpath)

    @property
    def body(self):
        """Construct JSON-compatible dict representation of DC/OS installation
        state descriptor.
        """
        if self._istor_nodes is None:
            istor_nodes = self._istor_nodes
        else:
            istor_nodes = {
                k: str(v) for k, v in self._istor_nodes._asdict().items()
            }

        return {
            'istor_nodes': istor_nodes,
            'istate': self._istate,
            'istate_dpath': str(self._istate_dpath),
        }

    @ classmethod
    def load(cls, fpath: Path):
        """Load DC/OS installation state descriptor from a file.

        :param fpath: Path, path to a JSON-formatted descriptor file.
        :return:      InstallationState, DC/OS installation state descriptor
                      object.
        """
        isd_body = cr_utl.rc_load_json(fpath, emheading=cls.__name__)

        # TODO: Add content verification (jsonschema) for m_body. Raise
        #       ValueError, if conformance was not confirmed.

        try:
            istor_nodes = IStorNodes(**{
                k: Path(v) for k, v in isd_body.get('istor_nodes').items()
            }) if isinstance(isd_body.get('istor_nodes'), dict) else None

            istate_desc = cls(
                istor_nodes=istor_nodes,
                istate=isd_body.get('istate'),
                istate_dpath=Path(isd_body.get('istate_dpath')),
                save=False,
            )
            LOG.debug(f'{cls.__name__}: Load: {fpath}')
        except (ValueError, AssertionError, TypeError) as e:
            err_msg = (f'{cls.__name__}: Load:'
                       f' {fpath}: {type(e).__name__}: {e}')
            raise cr_exc.RCInvalidError(err_msg) from e

        return istate_desc

    def save(self):
        """Save DC/OS installation state descriptor to a file within the
        installation's state directory."""
        fpath = self._istate_dpath.joinpath(cm_const.DCOS_INST_STATE_FNAME_DFT)

        try:
            self._istate_dpath.mkdir(parents=True, exist_ok=True)
            with fpath.open(mode='w') as fp:
                json.dump(self.body, fp)
        except (OSError, RuntimeError) as e:
            err_msg = f'{self.msg_src}: Save: {type(e).__name__}: {e}'
            raise cr_exc.RCError(err_msg) from e

        LOG.debug(f'{self.msg_src}: Save: {fpath}')

    @property
    def istor_nodes(self):
        """"""
        return self._istor_nodes

    @istor_nodes.setter
    def istor_nodes(self, istor_nodes: IStorNodes):
        """Set DC/OS installation storage layout part of the DC/OS installation
        state descriptor.

        :param istor_nodes: IStorNodes, DC/OS installation storage nodes (set
                            of pathlib.Path objects)
        """
        err_msg_base = f'{self.msg_src}: Set storage layout'

        if self._istor_nodes is not None:
            raise RuntimeError(f'{err_msg_base}: Already set')
        elif getattr(istor_nodes, ISTOR_NODE.STATE) != self._istate_dpath:
            raise ValueError(f'{err_msg_base}: Installation'
                             f' state directory mismatch: {istor_nodes}')

        self._istor_nodes = istor_nodes
        try:
            self.save()
        except cr_exc.RCError:
            self._istor_nodes = None
            raise

    @property
    def istate(self):
        """"""
        return self._istate

    @istate.setter
    def istate(self, istate: str):
        """Set DC/OS installation state code.

        :param istate: str, DC/OS installation state code
        """
        err_msg = f'{self.msg_src}: Set state: {istate}'

        if istate not in VALID_ISTATES:
            raise ValueError(err_msg)

        istate_former = self._istate
        self._istate = istate
        try:
            self.save()
        except cr_exc.RCError:
            self._istate = istate_former
            raise

    @property
    def istate_dpath(self):
        """"""
        return self._istate_dpath
