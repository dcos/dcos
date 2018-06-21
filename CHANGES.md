## DC/OS 1.10.8

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

### Notable changes

* Updated REX-Ray version to 0.11.2 (DCOS_OSS-3597) [rexray v0.11.2](https://github.com/rexray/rexray/releases/tag/v0.11.2)


### Fixed and improved


### Security Updates


## DC/OS 1.10.7

### Notable changes

* Includes Marathon version [1.5.8](https://github.com/dcos/dcos/pull/2707)  (DCOS_OSS-2352)

* Includes Mesos Version 1.4 [dcos-mesos-1.4.x-nightly-315d047](https://github.com/mesosphere/mesos/tree/dcos-mesos-1.4.x-nightly-315d047)

* Includes Metronome version [0.4.2](https://github.com/dcos/metronome/releases/tag/v0.4.2)


### Fixed and improved

* Increase the mesos executor registration timeout from 2 seconds to 20 seconds. (DCOS_OSS-2335)

* Consolidated the Exhibitor bootstrapping shortcut by atomically reading and writing the ZooKeeper PID file. (DCOS-14199)

* Block DC/OS install if mesos work dir or docker root dir is XFS but not mounted with ftype=1 (COPS-3158)

* DCOS-UI: Update the version to [1.10.6](https://github.com/dcos/dcos/pull/2788)


### Security Updates

* Disable the 3DES bulk encryption algorithm for Master Admin Router's TLS. (DCOS_OSS-3537)


## DC/OS 1.10.8

### Notable changes

### Fixed and improved

* Fixed ftype=1 check for dcos-docker (DCOS_OSS-3549)

### Security


### TODO: (skumaran) - Include CHANGES.md for 1.10.6 release.


## DC/OS 1.10.5

### Notable changes

### Fixed and improved

- DC/OS overlay networks now work with systemd networkd on modern CoreOS
  (DCOS_OSS-1790).
- DC/OS OAuth is now more resilient towards ZooKeeper latency spikes
  (DCOS_OSS-2041).

### Security

- Reduced software version information reported by Admin Router (DCOS-19765).


## DC/OS 1.10.4

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


### Security

* The DC/OS diagnostics bundle does no longer contain sensitive cluster
  configuration values related to AWS Cloudformation templates (DCOS-19327).


## DC/OS 1.10.3

A patch release of DC/OS Enterprise 1.10.3 was shipped on December 12th, 2017 to
fix a bug in a DC/OS Enterprise component. We have skipped (open) DC/OS release
1.10.3 to keep both variants in sync with each other.


## DC/OS 1.10.2

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

### Security

* The DC/OS OpenSSL library is now configured to not support TLS compression
  anymore (compression allows for the so-called CRIME attack) (DCOS-19452).

* Removed sensitive config values from diagnostics bundles and build output
  (DCOS_OSS-1795).


## DC/OS 1.10.1


## DC/OS 1.10.0
