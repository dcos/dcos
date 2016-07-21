# Pkgpanda packaging style guidelines

- All packages in dcos/dcos should be cloned using http so people without github ssh setup can build DC/OS
- There is a standard pyton package format which should be used for all python packages.
  - Source based / tarball based: [packages/python-pyyaml/build]
  - Wheel based: [packages/python-jinja2/build]
- Copy / move things precisely, shell globbing tends to do unexpected things which leads to a long time debugging
- When using the dcos-builder docker as the build environment, don't specify it at all in the buildinfo.json
- Don't manually put the bash `-e`, `-u`, -`o pipefail`, or `-x` inside of a build script, pkgpanda always adds them.
- Don't use .gitignore inside of `extra/` folders. It will result in dirty package builds
- Use requires for compile time dependencies, not runtime dependencies (reduces the amount of excessive rebuilding)
