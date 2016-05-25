"""Panda package builder

Reads a buildinfo file, uses it to assemble the sources and determine the
package version, then builds the package in an isolated environment along with
the necessary dependencies.

Usage:
  mkpanda [--repository-url=<repository_url>] [--dont-clean-after-build]
  mkpanda tree [--mkbootstrap] [--repository-url=<repository_url>] [<variant>]
"""

import sys
from os import getcwd, umask
from os.path import basename, normpath

from docopt import docopt

import pkgpanda.build.constants
from pkgpanda.build import (BuildError, PackageStore, build_package_variants,
                            build_tree)


def main():
    try:
        arguments = docopt(__doc__, version="mkpanda {}".format(pkgpanda.build.constants.version))
        umask(0o022)

        # Make a local repository for build dependencies
        if arguments['tree']:
            package_store = PackageStore(getcwd(), arguments['--repository-url'])
            build_tree(package_store, arguments['--mkbootstrap'], arguments['<variant>'])
            sys.exit(0)

        # Package name is the folder name.
        name = basename(getcwd())

        # Package store is always the parent directory
        package_store = PackageStore(normpath(getcwd() + '/../'), arguments['--repository-url'])

        # Check that the folder is a package folder (the name was found by the package store as a
        # valid package with 1+ variants).
        if name not in package_store.packages_by_name:
            print("Not a valid package folder. Didn't find any 'buildinfo.json' files.")
            sys.exit(1)

        # No command -> build package.
        pkg_dict = build_package_variants(
            package_store,
            name,
            not arguments['--dont-clean-after-build'])

        print("Package variants available as:")
        for k, v in pkg_dict.items():
            if k is None:
                k = "<default>"
            print(k + ':' + v)

        sys.exit(0)
    except BuildError as ex:
        print("ERROR: {}".format(ex))
        sys.exit(1)

if __name__ == "__main__":
    main()
