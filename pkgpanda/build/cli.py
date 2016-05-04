"""Panda package builder

Reads a buildinfo file, uses it to assemble the sources and determine the
package version, then builds the package in an isolated environment along with
the necessary dependencies.

Usage:
  mkpanda [--repository-url=<repository_url>] [--dont-clean-after-build]
  mkpanda tree [--mkbootstrap] [--repository-url=<repository_url>] [<variant>]
  mkpanda clean
"""

import sys
from os import getcwd, umask
from os.path import basename, exists, normpath

from docopt import docopt

import pkgpanda.build.constants
from pkgpanda.build import (BuildError, PackageStore, build_package_variants, build_tree,
                            clean)


def main():
    try:
        arguments = docopt(__doc__, version="mkpanda {}".format(pkgpanda.build.constants.version))
        umask(0o022)

        # Make a local repository for build dependencies
        if arguments['tree']:
            build_tree(getcwd(), arguments['--mkbootstrap'], arguments['--repository-url'], arguments['<variant>'])
            sys.exit(0)

        # Check for the 'build' file to verify this is a valid package directory.
        if not exists("buildinfo.json"):
            print("Not a valid package folder. No 'buildinfo.json' file.")
            sys.exit(1)

        # Package name is the folder name.
        name = basename(getcwd())

        # Only clean in valid build locations (Why this is after buildinfo.json)
        if arguments['clean']:
            clean(getcwd())
            sys.exit(0)

        package_store = PackageStore(normpath(getcwd() + '/../'))

        # No command -> build package.
        pkg_dict = build_package_variants(
            package_store,
            name,
            arguments['--repository-url'],
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
