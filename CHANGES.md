Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!

## DC/OS 1.10.12 (in development)

### Notable changes

* Updated REX-Ray version to 0.11.4 (DCOS_OSS-4316) (COPS-3961) [rexray v0.11.4](https://github.com/rexray/rexray/releases/tag/v0.11.4)

### Fixed and improved

* Fixed a bug in Admin Router's service endpoint as of which the DCOS_SERVICE_REQUEST_BUFFERING setting was not adhered to in all cases. (DCOS_OSS-4999)

* [MARATHON-8493](https://jira.mesosphere.com/browse/MARATHON-8493) Fixed precision bug associated with summing pod resources.

* [MARATHON-8498](https://jira.mesosphere.com/browse/MARATHON-8498) Fixed secrets validator when changing secret env.

* [MARATHON-8466](https://jira.mesosphere.com/browse/MARATHON-8466) Prohibit the use of reserve words in app and pod ids

* [COPS-4483](https://jira.mesosphere.com/browse/COPS-4483) Provide backward compatible way to produce container ports for text/plain GET requests against /v2/tasks when using USER networking consistent with Marathon 1.4.

### Security updates

* The configuration parameters `aws_secret_access_key` and `exhibitor_azure_account_key` for exhibitor are now marked as secret and will thus not be revealed in `user.config.yaml` on cluster nodes but will from now on appear only in `user.config.full.yaml` which has stricter read permissions and is not included in DC/OS Diagnostics bundles. (DCOS-51751)


## DC/OS 1.10.11 (2019-02-12)

### Security updates

* Addressed a vulnerability in the Mesos Docker containerizer by enabling a concept called "Mesos containerizer launcher sealing". This type of vulnerability was widely discussed under ID CVE-2019-5736.


## DC/OS 1.10.10 (2019-01-29)

### Notable changes

* Added support for CoreOS 1800.6.0 1800.7.0, & 1855.4.0. (DCOS_43865)

* Master Admin Router: the UI is now served with the `X-Frame-Options` header set to `SAMEORIGIN`. (DCOS-45280)

### Fixed and improved

* Docker-GC will now log to journald. (DCOS_OSS-4469, COPS-4044)

* Minuteman routes traffic until the first failed health check. (DCOS_OSS-1954)

* Mesos now exposes a flag to allow the network CNI root directory to be persisted across host reboot. (DCOS_OSS-4667)


## DC/OS 1.10.9 (2018-1-06)

### Notable changes

* Updated to Marathon [1.5.12](https://github.com/mesosphere/marathon/releases/tag/v1.5.12)

* Updated DC/OS UI to [v1.10.9](https://github.com/dcos/dcos-ui/releases/tag/v1.10+v1.10.9)

### Fixed and improved

* Get timestamp on dmesg, timedatectl, distro version, systemd unit status and pods endpoint in diagnostics bundle. (DCOS_OSS-3861)

* Set Master Admin Router's `access_log` syslog facility to `daemon`. (DCOS-38622)

* Admin Router: Change 'access_log' syslog facility from 'local7' to 'daemon'. (DCOS_OSS-3793)

* Increased Agent Admin Router's `worker_connections` to 10000 to allow for a large number of tasks to be run on a single node. (DCOS-37833)

* Consolidated Exhibitor startup script to abort when the IP address returned by 'ip-detect' is not contained in the known master IP address list. This fixes issues arising from transient errors in the 'ip-detect' script. (COPS-3195)

* Root Marathon support for post-installation configuration of flags and JVM settings has been improved. (DCOS_OSS-3556)

### Security updates

* Prevent dcos-history from leaking authentication tokens. (DCOS-40373)

* Updated Java to 8u192. (DCOS_OSS-4383)


## DC/OS 1.10.8 (2018-07-19)

### Notable changes

* Updated REX-Ray version to 0.11.2 (DCOS_OSS-3597) [rexray v0.11.2](https://github.com/rexray/rexray/releases/tag/v0.11.2)

* Includes Marathon [1.5.11](https://github.com/mesosphere/marathon/releases/tag/v1.5.11)

### Fixed and improved

* L4LB unstable when something is deployed in the cluster (DCOS_OSS-3602)

* Root Marathon heap size can be customized during installation. (DCOS_OSS-3556)

* Add task labels as tags on container metrics (DCOS_OSS-3304)

* Increase the mesos agent response timeout for dcos-metrics (DCOS-37452)

* Prevent cosmos-specific labels being sent as metrics tags (DCOS-37451)

* Improve the way statsd timers are handled in dcos-metrics (DCOS-38083)



## DC/OS 1.10.7 (2018-05-24)

### Notable changes

* Includes Marathon version [1.5.8](https://github.com/dcos/dcos/pull/2707)  (DCOS_OSS-2352)

* Includes Mesos Version 1.4 [dcos-mesos-1.4.x-nightly-315d047](https://github.com/mesosphere/mesos/tree/dcos-mesos-1.4.x-nightly-315d047)

* Includes Metronome version [0.4.2](https://github.com/dcos/metronome/releases/tag/v0.4.2)

### Fixed and improved

* Increase the mesos executor registration timeout from 2 seconds to 20 seconds. (DCOS_OSS-2335)

* Consolidated the Exhibitor bootstrapping shortcut by atomically reading and writing the ZooKeeper PID file. (DCOS-14199)

* Block DC/OS install if mesos work dir or docker root dir is XFS but not mounted with ftype=1 (COPS-3158)

* DCOS-UI: Update the version to [1.10.6](https://github.com/dcos/dcos/pull/2788)

### Security updates

* Disable the 3DES bulk encryption algorithm for Master Admin Router's TLS. (DCOS_OSS-3537)


## DC/OS 1.10.6 (2018-04-24)

Todo: needs to be back-filled

### Notable changes

### Fixed and improved

* Fixed ftype=1 check for dcos-docker (DCOS_OSS-3549)

### Security updates


## DC/OS 1.10.5 (2018-02-22)

### Notable changes

### Fixed and improved

* DC/OS overlay networks now work with systemd networkd on modern CoreOS
  (DCOS_OSS-1790).

* DC/OS OAuth is now more resilient towards ZooKeeper latency spikes
  (DCOS_OSS-2041).

### Security updates

- Reduced software version information reported by Admin Router. (DCOS-19765)


## DC/OS 1.10.4 (2018-01-16)

### Notable changes

* Updated to [Mesos 1.4.1](http://mesos.apache.org/blog/mesos-1-4-1-released/).

* Updated to [Marathon 1.5.5](https://github.com/mesosphere/marathon/releases).

* Updated to Metronome 0.3.2.

* Platform: the Java Developer Kit was upgraded to JDK 8u152.

* DC/OS is now compatible with Docker version 17.05.0.

### Fixed and improved

* The Mesos libprocess thread pool size has been increased from 8 to 16 in order
  to avoid potential deadlocks when interacting with ZooKeeper (DCOS_OSS-1943).
* The DC/OS CLI can now retrieve metrics for tasks running in the Docker
  containerizer (DCOS_OSS-1898).
* DC/OS bootstrap now is more resilient towards a missing process ID file while
  waiting for Exhibitor to equilibrate (DCOS_OSS-1919).
* Fixed a crash condition in the DC/OS networking stack (DCOS-19893).

### Security updates

* The DC/OS diagnostics bundle does no longer contain sensitive cluster
  configuration values related to AWS Cloudformation templates (DCOS-19327).


## DC/OS 1.10.3 (2017-12-12)

A patch release of DC/OS Enterprise 1.10.3 was shipped on December 12th, 2017 to
fix a bug in a DC/OS Enterprise component. We have skipped (open) DC/OS release
1.10.3 to keep both variants in sync with each other.


## DC/OS 1.10.2 (2017-11-30)

### Notable changes

* Updated to [Mesos 1.4.0](https://git-wip-us.apache.org/repos/asf?p=mesos.git;a=blob_plain;f=CHANGELOG;hb=1.4.0).

* Updated to [Marathon 1.5.2](https://github.com/mesosphere/marathon/releases/tag/v1.5.2).

* DC/OS is not compatible with RHEL 7.4.

### Fixed and improved

* The DC/OS CLI now ignores output when opening a browser window so that users
  do not see error information when prompted for the authentication token
  (DCOS_OSS-1508).

* DC/OS Metrics now sanitizes metrics names (DCOS_OSS-1818).

* DC/OS layer 4 load balancer now periodically checks that the IPVS
  configuration matches the desired configuration and reapplies if the
  configuration is absent (DCOS_OSS-1825).

* The DC/OS CLI can now retrieve metrics for DC/OS data services (DCOS-19009).

* Docs: updated configuration example for a cluster that uses custom Docker credentials (DCOS-17947).

* Docs: clarified how operators can recover from a full agent disk (DOCS-1925).

### Security updates

* The DC/OS OpenSSL library is now configured to not support TLS compression
  anymore (compression allows for the so-called CRIME attack) (DCOS-19452).

* Removed sensitive config values from diagnostics bundles and build output
  (DCOS_OSS-1795).


## DC/OS 1.10.1 (2017-11-01)


## DC/OS 1.10.0 (2017-09-08)
