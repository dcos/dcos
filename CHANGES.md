Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!


## DC/OS 2.1.0 (in development)


### What's new

* Switched from Oracle Java 8 to OpenJDK 8 (DCOS-54902)

* Updated DC/OS UI to [master+v2.148.8](https://github.com/dcos/dcos-ui/releases/tag/master+v2.148.8).

* Updated to [Mesos 1.9.0-rc3](https://github.com/apache/mesos/blob/5e79a584e6ec3e9e2f96e8bf418411df9dafac2e/CHANGELOG). (DCOS_OSS-5342)

* Mesos overlay networking: support dropping agents from the state. (DCOS_OSS-5536)

### Breaking changes


### Fixed and improved

* Update CNI to 0.7.6

* Fixes increasing diagnostics job duration when job is done (DCOS_OSS-5494)

* Remove the octarine package from DC/OS. It was originally used as a proxy for the CLI but is not used for this purpose, anymore.
