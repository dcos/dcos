"""Panda package management for Windows.

DC/OS package ID type definition.
"""

from typing import Tuple


class PackageId:
    """DC/OS package ID type.

    Ref:
      [1] https://github.com/dcos/dcos/blob/master/pkgpanda/docs/\
          package_concepts.md
    """
    _separator = '--'

    def __init__(self, pkg_id: str = "", pkg_name: str = "",
                 pkg_version: str = ""):
        """Constructor.

        :param pkg_id:      str, string representation of a DC/OS package ID
        :param pkg_name:    str, DC/OS package name
        :param pkg_version: str, DC/OS package version
        """
        # TODO: Add character set validation for arguments [1]
        if pkg_id:
            pkg_name, sep, pkg_version = str(pkg_id).partition(self._separator)

            if not (sep and pkg_name and pkg_version):
                raise ValueError(f'Invalid package ID: {pkg_id}')

            self.pkg_name = pkg_name
            self.pkg_version = pkg_version
            self.pkg_id = pkg_id
        elif pkg_name and pkg_version:
            self.pkg_name = str(pkg_name)
            self.pkg_version = str(pkg_version)
            self.pkg_id = f'{self.pkg_name}{self._separator}{self.pkg_version}'

    def __str__(self) -> str:
        return self.pkg_id

    @classmethod
    def parse(cls, pkg_id: str) -> Tuple:
        """Deconstruct a package ID string into elements.

        :param pkg_id: str, string representation of a DC/OS package ID
        :return:       tuple(str, str), two tuple of package ID elements -
                       (pkg_name, pkg_version)
        """
        pkg_name, sep, pkg_version = str(pkg_id).partition(sep=cls._separator)
        if not (sep and pkg_name and pkg_version):
            raise ValueError(f'Invalid package ID: {pkg_id}')

        return pkg_name, pkg_version
