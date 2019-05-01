```
* For any significant improvement to DC/OS add an entry to Fixed and Improved section.
* For Security updates, please call out in Security updates section.
* Add to the top of the existing list.
* External Projects like Mesos and Marathon shall provide a link to their published changelogs.

Format of the entries must be.

* Entry with no-newlines. (DCOS_OSS_JIRA)
<new-line>
* Entry two with no-newlines. (DCOS_OSS_JIRA_2)
```


## DC/OS 1.11.11 (in development)

### Notable changes

* Updated urllib3 version to 1.24.2 due to: https://nvd.nist.gov/vuln/detail/CVE-2019-11324. (DCOS-52210)

### Fixed and improved

* `docker-gc` now removes unused volumes (DCOS_OSS-1502)

* Fix a bug in Admin Router's service endpoint as of which the DCOS_SERVICE_REQUEST_BUFFERING setting was not adhered to in all cases. (DCOS_OSS-4999)

* Fix dcos-net-setup.py failing when systemd network directory did not exist (DCOS-49711)

* Fix a race condition in L4LB (DCOS_OSS-4939)

* Updated REX-Ray version to 0.11.4 (DCOS_OSS-4316) (COPS-3961) [rexray v0.11.4](https://github.com/rexray/rexray/releases/tag/v0.11.4)

 * The configuration parameters `aws_secret_access_key` and `exhibitor_azure_account_key` for exhibitor are now marked as secret and will thus not be revealed in `user.config.yaml` on cluster nodes but will from now on appear only in `user.config.full.yaml` which has stricter read permissions and is not included in DC/OS Diagnostics bundles. (DCOS-51751)

* Conflict between VIP port and port mapping (DCOS_OSS-4970)

### Security updates

* Update to OpenSSL 1.0.2r. (DCOS_OSS-4868)



## DC/OS 1.11.10

### Notable changes

### Fixed and improved

* Improve error message in case Docker is not running at start of installation (DCOS-15890)

* Stop requiring `ssh_user` attribute in `config.yaml` when using parts of deprecated CLI installer (DCOS_OSS-4613)



## DC/OS 1.11.9

* [Marathon 1.6.567](https://github.com/mesosphere/marathon/tree/2d8b3e438ffcc536ccf8b1ea9cb0b39bb3ef4e10).

* [Metronome 0.4.5](https://github.com/dcos/metronome/tree/8d6c6b9cd7ab6f88d70cfff5f4d10f29b81d0a6b)

* [Mesos 1.5.x](https://github.com/apache/mesos/tree/5f6225bd6e039c633b7758f02d2b5fbabc8e0169)

### Notable changes

* Run dcos-diagnostics as the `root` user (DCOS_OSS_3877)

### Fixed and improved

* Updated to [DC/OS UI 1.11+v1.26.0](https://github.com/dcos/dcos-ui/blob/1.11+v1.26.0/CHANGELOG.md)

* Add SELinux details to diagnostics bundle (DCOS_OSS-4123)

* Add external Mesos master/agent logs in the diagnostic bundle (DCOS_OSS-4283)

* Allow dcos-diagnostics bundles location to be configured (DCOS_OSS-4040)

* Fixed a bug that caused the Prometheus exporter to omit some metrics. (DCOS_OSS-3863)

* Docker-GC will now log to journald. (COPS-4044)

* Mark `dcos6` overlay network as disabled if `enable_ipv6` is set to false (DCOS-40539)

* Expose a Mesos flag to allow the network CNI root directory to be persisted across host reboot. (DCOS_OSS-4667)

* Make cluster identity configurable in dcos-net (DCOS_OSS-4620)

* Mark `dcos6` overlay network as disabled if `enable_ipv6` is set to false (DCOS-40539)

### Security Updates

* Upgraded the requests library used i DC/OS to 2.21.0 to address CVE-2018-18074,  CVE-2018-18074, 
  both of which were Moderate severity reports. (DCOS_OSS-4418)


## DC/OS 1.11.8

### Notable changes

* Updated to [Marathon 1.6.567](https://github.com/mesosphere/marathon/tree/2d8b3e438ffcc536ccf8b1ea9cb0b39bb3ef4e10).

* Updated to [DC/OS UI 1.11+v1.26.0](https://github.com/dcos/dcos-ui/blob/1.11+v1.26.0/CHANGELOG.md)

* Update to [Metronome 0.4.5](https://github.com/dcos/metronome/tree/8d6c6b9cd7ab6f88d70cfff5f4d10f29b81d0a6b)

* dcos-net continously restarting systemd-networkd on a bare-metal server with bond interfaces (DCOS_OSS-4398)

* Minuteman routes traffic until the first failed health check (DCOS_OSS-1954)

* Docker container unable to curl its own VIP (DCOS-45115)

* [DCOS_OSS-3616](https://jira.mesosphere.com/browse/DCOS_OSS-3616) Metronome is hoarding offers.

* [DCOS_OSS-2535](https://jira.mesosphere.com/browse/DCOS_OSS-2535) Info endpoint shows incorrect version of Metronome.


### Security Updates

* Update Java to 8u192. (DCOS_OSS-4382)


## DC/OS 1.11.7

### Notable changes

* Updated to [Marathon 1.6.564](https://github.com/mesosphere/marathon/tree/3fa693b32).

* Updated to [DC/OS UI 1.11+v1.24.0](https://github.com/dcos/dcos-ui/blob/1.11+v1.24.0/CHANGELOG.md)

### Fixed and improved

* Get timestamp on dmesg, timedatectl, distro version, systemd unit status and pods endpoint in diagnostics bundle. (DCOS_OSS-3861)

* DC/OS Metrics: Fixed a bug that was crashing the DC/OS agent metrics service (DCOS-39103)

* [DCOS-42753](https://jira.mesosphere.com/browse/DCOS-42753) Bump Akka library to fix memory leak issue.
* [MARATHON-8453](https://jira.mesosphere.com/browse/MARATHON-8453) TaskOverdueActor now respects `--kill_retry_timeout`.
* [MARATHON-8452](https://jira.mesosphere.com/browse/MARATHON-8452) Only log zero-value offers for scalar resources.
* [MARATHON-8461](https://jira.mesosphere.com/browse/MARATHON-8461) Write correct version in Zkid (based on scala timestamp changes)
* [MARATHON-8413](https://jira.mesosphere.com/browse/MARATHON-8413) Fix versioning for Apps and Pods based on timestamp changes.
* [MARATHON-8420](https://jira.mesosphere.com/browse/MARATHON-8420) Marathon behavior has changed to fail if service is torn down in mesos but the frameworkid is in zk.
* [MARATHON-7941](https://jira.mesosphere.com/browse/MARATHON-7941) Default for unreachable strategy on PUT /apps.
* [MARATHON-8323](https://jira.mesosphere.com/browse/MARATHON-8323) Increase http proxy max-open-connections default.


### Security Updates


## DC/OS 1.11.6

### Notable changes

* Updated to [Metronome 0.4.4](https://github.com/dcos/metronome/releases/tag/v0.4.4).

* Updated to [DC/OS UI 1.11+v1.23.0](https://github.com/dcos/dcos-ui/blob/1.11+v1.23.0/CHANGELOG.md)

* Updated to [ZooKeeper 3.4.13](https://zookeeper.apache.org/doc/r3.4.13/releasenotes.html).

* Updated to [Marathon 1.6.549](https://github.com/mesosphere/marathon/tree/aabf74302).


### Fixed and improved

* Diagnostics bundle: include new information in bundle (container status and usage info, process list, Mesos quota info). (DCOS-38438, COPS-3042)

* Root Marathon: consolidated task_launch_confirm and task_reservation timeouts. (DCOS-39290)

### Security updates

 * Updated OpenSSL to version 1.0.2p. (DCOS_OSS-4105)


## DC/OS 1.11.5

### Notable changes

* Updated to [DC/OS UI 1.11+v1.19.0](https://github.com/dcos/dcos-ui/blob/1.11+v1.19.0/CHANGELOG.md)

### Fixed and improved

* Consolidated Exhibitor startup script to abort when the IP address returned by 'ip-detect' is not contained in the known master IP address list. This fixes issues arising from transient errors in the 'ip-detect' script. (COPS-3195)

* Fixed Docker isolation iptables rule reversal on reboot. (DCOS_OSS-3697)

* Updated CNI plugins to v0.7.1. (DCOS_OSS-3841)

### Security updates

* Update Java to 8u181. (DCOS_OSS-3932)

* Prevent dcos-history leaking auth tokens (DCOS-40373)


## DC/OS 1.11.4


### Notable changes

* Updated REX-Ray version to 0.11.2 (DCOS_OSS-3597) [rexray v0.11.2](https://github.com/rexray/rexray/releases/tag/v0.11.2)
* Updated to [DC/OS UI 1.11+v1.17.0](https://github.com/dcos/dcos-ui/blob/1.11+v1.17.0/CHANGELOG.md)


### Fixed and improved

* Admin Router: Change 'access_log' syslog facility from 'local7' to 'daemon'. (DCOS_OSS-3793)

* L4LB unstable when something is deployed in the cluster (DCOS_OSS-3602)

* Prevent metric names beginning with a number in prometheus output (DCOS_OSS-2360)

* Add task labels as tags on container metrics (DCOS_OSS-3304)

* Increase the mesos agent response timeout for dcos-metrics (DCOS-37452)

* Prevent cosmos-specific labels being sent as metrics tags (DCOS-37451)

* Improve the way statsd timers are handled in dcos-metrics (DCOS-38083)

* Fix logging of dcos-checks-poststart results to the journal. (DCOS_OSS-3804)

* CNI module now stores configuration on a tmpfs dir, allocated IP addresses are recycled upon agent reboot. (DCOS_OSS-3750)

* Add debug route to metrics API (DCOS-37454)

* Add per-framework metrics to the Mesos master (DCOS_OSS-3991)

### Security updates


## DC/OS 1.11.3


### Notable changes

* Support for CoreOS 1688.4.0, 1688.5.3. (DCOS_OSS-2417, DCOS_OSS-3548)

* Updated to [DC/OS UI 1.11+v1.14.0](https://github.com/dcos/dcos-ui/blob/1.11+v1.14.0/CHANGELOG.md)

* Updated to [Marathon 1.6.496](https://github.com/dcos/dcos/pull/2678).


### Fixed and improved

* Added check in custom installer for ftype=1 on Mesos and Docker work directories if using XFS. (COPS-3158)

* Increase the limit of Cosmos

* DCOS Cosmos: Increase the limit of max-payload size at /v2/apps Marathon end point. (DCOS-34435)

* Root Marathon support for post-installation configuration of flags and JVM settings has been improved. (DCOS_OSS-3556)

* Root Marathon heap size can be customized during installation. (DCOS_OSS-3556)

### Security updates


## DC/OS 1.11.2


### Notable changes

* Updated to [Mesos 1.5.1-dev](https://github.com/mesosphere/mesos/blob/27d91e1fe46f09b2c74f2dc4efe4f58ae59ae0a8/CHANGELOG).

* Updated to [Marathon 1.6.392](https://github.com/dcos/dcos/pull/2678).

* Updated to [Metronome 0.4.2](https://github.com/dcos/metronome/releases/tag/v0.4.2).


### Fixed and improved

* Updated DC/OS UI to [1.11+v1.14.0](https://github.com/dcos/dcos-ui/blob/1.11+v1.14.0/CHANGELOG.md)

* DC/OS Metrics: metric names are now sanitized for better compatibility with Prometheus. (DCOS_OSS-2360)

* Reverted the Marathon configuration change for GPU resources which was introduced with the 1.11.1 release. (MARATHON-8090)

* The IP detect script and fault domain detect script may now be changed with a config upgrade. (DCOS-21611)

* Upgraded Erlang/OTP runtime to address a race condition in TLS connection establishment. (DCOS_OSS-2378)

* Consolidated pkgpanda's package download method. (DCOS_OSS-2317)

* Consolidated the Exhibitor bootstrapping shortcut by atomically reading and writing the ZooKeeper PID file. (DCOS-14199)

* Increased the Mesos executor reregistration timeout to consolidate an agent failover scenario. (DCOS_OSS-2335)

* DC/OS UI: incorporated [multiple](https://github.com/dcos/dcos/pull/2799) fixes and improvements.


### Security updates

* Admin Router on the DC/OS master nodes now does not support TLS 1.1 and the 3DES bulk encryption algorithm anymore by default. (DCOS-21958)


## DC/OS 1.11.1


### Notable changes

* Updated to [Mesos 1.5.1-dev](https://github.com/mesosphere/mesos/blob/b2eeb11ede805a7830cd6fb796d0b21a647aba04/CHANGELOG).

* Updated to [Marathon 1.6.352](https://github.com/mesosphere/marathon/releases).

* Updated to [Metronome 0.4.1](https://github.com/dcos/metronome/releases/tag/v0.4.1).

* Added support for CoreOS 1632.2.1. (DCOS_OSS-2130)

* Moved Prometheus producer to port 61091. (DCOS-21545)


### Fixed and improved

* DC/OS checks: Update checks timeout

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
