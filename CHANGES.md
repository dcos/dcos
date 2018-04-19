## DC/OS 1.11.2


### Notable changes


### Fixed and improved


### Security updates


## DC/OS 1.11.1


### Notable changes

* Updated to [Mesos 1.5.1-dev](https://github.com/mesosphere/mesos/blob/b2eeb11ede805a7830cd6fb796d0b21a647aba04/CHANGELOG).

* Updated to [Marathon 1.5.5](https://github.com/mesosphere/marathon/releases).

* Updated to [Metronome 0.4.1](https://github.com/dcos/metronome/releases/tag/v0.4.1).

* Added support for CoreOS 1632.2.1. (DCOS_OSS-2130)

* Moved Prometheus producer to port 61091. (DCOS-21545)


### Fixed and improved

* Admin Router: Fixed a bug where Mesos leader changes would not be picked up (leading to unexpected 404 HTTP responses when using the service endpoint). (DCOS-21451)

* Networking: Landed performance improvements and bug fixes in [lashup](https://github.com/dcos/lashup). (DCOS_OSS-2229)

* Networking: Enhanced compatibility with Kubernetes. (DCOS-21486)

* DC/OS checks: Fixed handling of the --detect-ip flag. (DCOS_OSS-1878)

* DC/OS checks: Fixed a bug where a command timeout was treated as a failed check. (DCOS_OSS-2247)

* Cosmos: Improved readability on user-facing messages during service uninstallation. (DCOS_OSS-2087)

* Cosmos: Updated package-manager.yaml to fix a schema error in the package management API. (DCOS_OSS-1759)

* Cosmos: Fixed a crash upon uninstalling Marathon apps that don't define `env`. (DCOS-21374)

* DC/OS UI: Improved error handling when consuming the Mesos event streaming HTTP API. (DCOS-21337)

* DC/OS UI: Fixed file navigation when browsing task sandbox. (DCOS-21266)

* DC/OS UI: Fixed a scenario in which the services tab crashed after uninstalling a service. (DCOS-21128)

* DC/OS UI: Implemented a region picker for region awareness. (INFINITY-3358)

* DC/OS UI: Fixed a TypeError upon service uninstallation. (DCOS-21359)

* DC/OS UI: Added a placement constraint validator to the service creation view. (DCOS-19648)

* DC/OS log: consolidated handling of journald log file rotation. (DCOS_OSS-2132)

* DC/OS CLI: Fixed rare situations where dcos task --follow task might crash. (DCOS_OSS-2292)

* Fixed an edge case as of which the history service would crash-loop. (DCOS_OSS-2210)

* Consolidated Marathon's configuration in DC/OS for GPU resources. (MARATHON-8090)

* Improved error reporting when sanity checks fail after an upgrade. (DCOS_OSS-2028)

* Introduced 'minimal DC/OS version' when installing universe packages (e.g., cannot install a package which requires DC/OS 1.11 on DC/OS 1.10). (DCOS-21305)


### Security updates

* Mesos does not expose ZooKeeper credentials anymore via its state JSON document. (DCOS_OSS-2162)

* Updated cURL to version 7.59. (DCOS-21557)

* Updated OpenSSL to version 1.0.2n. (DCOS_OSS-1903)


## DC/OS 1.11.0


### What's new


### Breaking changes
