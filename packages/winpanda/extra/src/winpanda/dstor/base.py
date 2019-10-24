"""Winpanda: DC/OS distribution storage: Base driver interface definition.
"""
import abc

DSTOR_TYPES = {}


def create(dse_opts, *args, **kwargs):
    """Instantiate a DC/OS distribution storage interface object.

    :param dse_opts: dict, distribution storage endpoint specification
    """
    dse_scheme = dse_opts.get('scheme')

    return DSTOR_TYPES[dse_scheme](dse_opts, *args, **kwargs)


def dstor_type(scheme):
    """Register a DC/OS distribution storage class in the distribution storage
    types registry.

    :param scheme: str, data access protocol
    """
    def decorator(cls):
        """"""
        DSTOR_TYPES[scheme] = cls
        return cls

    return decorator


class DistStorage(metaclass=abc.ABCMeta):
    """Abstract base class for DC/OS distribution storage driver types.
    """
    def __init__(self, dse_opts, *args, **kwargs):
        """Constructor.
        """
        self.dse_opts = dse_opts
        self.dse_scheme = self.dse_opts.get('scheme')
        self.ds_client = None

    def __repr__(self):
        return (
            '<%s(dse="%s")>' % (self.__class__.__name__, self.dse_opts)
        )

    def __str__(self):
        return self.__repr__()

    @abc.abstractmethod
    def verify_dse_options(self, *args, **kwargs):
        """Verify distribution storage endpoint options.
        """
        pass

    @abc.abstractmethod
    def get_package(self, *args, **kwargs):
        """Retrieve DC/OS component package.
        """
        pass
