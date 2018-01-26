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