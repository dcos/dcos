# Tree Concepts

In the [package directory](../../packages), the only things that can be placed there besides package-folders is a `*treeinfo.json` file and an `upstream.json` file. A `*treeinfo.json` describes an arbitrary set of packages and how they should be bundled into a bootstrap tarball.

## treeinfo.json
Normally, all packages in the package directory are considered a part of the target set to be added to the bootstrap tarball, but a `*treeinfo.json` allows specifying subsets which we call variants. For example, a `foobar.treeinfo.json` would describe how to build the foobar variant. By default, all packages are a part of the `<default>` variant.  Specifically, consider [treeinfo.json](../../packages/treeinfo.json), which is such a tree for the "default" variant:
```
{
  "exclude": [
    "dcos-installer-ui"
  ],
  "bootstrap_package_list": ["dcos-image"]
}
```
The "exclude" field is to say that the package `"dcos-installer-ui"` should not be built in the default variant. The `"bootstrap_package_list"` is a whitelist of packages that will be placed in the default bootstrap tarball. The bootstrap tarball is the collection of packages transferred to host machines which then orchestrates the bootstrapping of the remaining packages to spin up DC/OS. As such, the installer UI code is completely useless to a DC/OS deployment.

Now, if we consider [installer.treeinfo.json](../../packages/installer.treeinfo.json):
```
{
  "core_package_list": [
    "dcos-image",
    "dcos-installer-ui"
  ]
}
```
The `"core_package_list"` field declares a whitelist of packages that are to be built and packaged into the bootstrap tarball for the variant `installer`.

The purpose of the above configuration is to generate two bootstrap tarballs with each build. The default tarball will contain the code that handles the import of the remaining DC/OS packages (as dictated by the provider `gen.build_deploy` module) and setup the hosts to startup DC/OS. The installer tarball will be used to create a mock DC/OS environment which can provide packages to hosts via the `dcos_installer` program (see below). It is important to note the distinction that `installer` is a bootstrap variant, and not a DC/OS variant. Thus, in a new variant `installer.foobar.treeinfo.json` would allow crafting a variant onprem installer for the `foobar` DC/OS variant.

## Package Variants
 To have a package variant built, the `treeinfo.json` must have a `"variant"` section that describes the specific package variant to be used with the tree variant. This logic must be done explicitly as there is no implicit matching between package and tree variants. E.G. if one wanted to have a variant of mesos to build called `foobar`, one must:
* add a variant source `foobar.buildinfo.json` to the mesos package
* create a treeinfo.json or update the default treeinfo.json to include:
```
{
  "variants": {
    "mesos": "foobar"
  }
}
```

## upstream.json
The other file that can be placed in the `packages` directory is called `upstream.json`. This JSON is formatted as a single source from the aforementioned `buildinfo.json`. Here's an example:
```
{
  "git": "https://github.com/dcos/dcos",
  "kind": "git",
  "ref": "9364e0a72b942e8dcec306ef7c1673c6f23bd9cc",
  "ref_origin": "master"
}
```
This file will tell pkgpanda the packages directory containing it should be expanded to include the packages from the given upstream source. Note, if a package needs to interact with its own upstream variant, then one could constuct a `buildinfo.json` like so:
```
{
  "requires": ["foo"],
  "sources": {
    "some_lib": {
      "kind": "url_extract",
      "url": "https://pypi.python.org/some_lib.tar.gz",
      "sha1": "40bdb9c829627dac345c781a24a247bbf5d5b255"
    },
    "dcos": {
      "kind": "git_local",
      "rel_path": "../cache/upstream/checkout"
    }
  }
}
```
Thus, one may create a modified version of DC/OS by just defining the desired package modifications; no forked repositories required! Note: only the treeinfo.json present in the non-upstream directory will be be built.
