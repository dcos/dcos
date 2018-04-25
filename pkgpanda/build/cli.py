"""Panda package builder

Reads a buildinfo file, uses it to assemble the sources and determine the
package version, then builds the package in an isolated environment along with
the necessary dependencies.

Usage:
  mkpanda [--repository-url=<repository_url>] [--dont-clean-after-build] [--recursive] [--variant=<variant>]
  mkpanda tree [--mkbootstrap] [--repository-url=<repository_url>] [--variant=<variant>]
"""

import sys
from os import getcwd, umask
from os.path import basename, normpath

from docopt import docopt

import pkgpanda.build
import pkgpanda.build.constants


def main():
    try:
        arguments = docopt(__doc__, version="mkpanda {}".format(pkgpanda.build.constants.version))
        umask(0o022)
        variant_arg = arguments['--variant']
        # map the keyword 'default' to None to build default as this is how default is internally
        # represented, but use the None argument (i.e. the lack of variant arguments) to trigger all variants
        target_variant = variant_arg if variant_arg != 'default' else None
        # Make a local repository for build dependencies
        if arguments['tree']:
            package_store = pkgpanda.build.PackageStore(getcwd(), arguments['--repository-url'])
            if variant_arg is None:
                pkgpanda.build.build_tree_variants(package_store, arguments['--mkbootstrap'])
            else:
                pkgpanda.build.build_tree(package_store, arguments['--mkbootstrap'], [target_variant])
            sys.exit(0)

        # Package name is the folder name.
        name = basename(getcwd())

        # Package store is always the parent directory
        package_store = pkgpanda.build.PackageStore(normpath(getcwd() + '/../'), arguments['--repository-url'])

        # Check that the folder is a package folder (the name was found by the package store as a
        # valid package with 1+ variants).
        if name not in package_store.packages_by_name:
            print("Not a valid package folder. Didn't find any 'buildinfo.json' files.", file=sys.stderr)
            sys.exit(1)

        clean_after_build = not arguments['--dont-clean-after-build']
        recursive = arguments['--recursive']
        if variant_arg is None:
            # No command -> build all package variants.
            pkg_dict = pkgpanda.build.build_package_variants(
                package_store,
                name,
                clean_after_build,
                recursive)
        else:
            # variant given, only build that one package variant
            pkg_dict = {
                target_variant: pkgpanda.build.build(
                    package_store,
                    name,
                    target_variant,
                    clean_after_build,
                    recursive)
            }

        print("Package variants available as:")
        for k, v in pkg_dict.items():
            if k is None:
                k = "<default>"
            print(k + ':' + v)

        sys.exit(0)
    except pkgpanda.build.BuildError as ex:
        print("ERROR: {}".format(ex))
        sys.exit(1)


if __name__ == "__main__":
    main()
