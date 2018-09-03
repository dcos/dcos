## DC/OS 1.12.0

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


### Fixed and improved
* Add mountinfo to diagnostics bundle (DCOS_OSS_3961)

* Fixed Docker isolation iptables rule reversal on reboot. (DCOS_OSS-3697)

* Updated CNI plugins to v0.7.1. (DCOS_OSS-3841)

* Mesos: Expose memory profiling endpoints. (DCOS_OSS-2137)

* Added an API for checks at /system/checks/ on all cluster nodes. (DCOS_OSS-1406)

* Admin Router: Change 'access_log' syslog facility from 'local7' to 'daemon'. (DCOS_OSS-3793)

* Node and cluster checks are executed in parallel. (DCOS_OSS-2239)

* Enabled Windows-based pkgpanda builds. (DCOS_OSS-1899)

* DC/OS Metrics: moved the prometheus producer from port 9273 to port 61091. (DCOS_OSS-2368)

* Release cosmos v0.6.0. (DCOS_OSS-2195)

* Added a DC/OS API endpoint to distinguish the 'open' and 'enterprise' build variants. (DCOS_OSS-2283)

* A cluster's IP detect script may be changed with a config upgrade (DCOS_OSS-2389)

* DC/OS Net: Support Mesos Windows Agent (DCOS_OSS-2073)

* DC/OS Net: Use Operator HTTP API (DCOS_OSS-1566)

* Admin Router: It is now possible to disable HTTP request buffering for `/service/` endpoint requests through the DCOS_SERVICE_REQUEST_BUFFERING Marathon label. (DCOS_OSS-2420)

* Admin Router: It is now possible to disable upstream request URL rewriting for `/service/` endpoint requests through the DCOS_SERVICE_REWRITE_REQUEST_URLS Marathon label. (DCOS_OSS-2420)

* Fixed ftype=1 check for dcos-docker (DCOS_OSS-3549)

* Root Marathon support for post-installation configuration of flags and JVM settings has been improved. (DCOS_OSS-3556)

* Root Marathon heap size can be customized during installation. (DCOS_OSS-3556)

* Fix logging of dcos-checks-poststart results to the journal. (DCOS_OSS-3804)

* Get timestamp on dmesg, timedatectl, distro version, systemd unit status and pods endpoint in diagnostics bundle. (DCOS_OSS-3861)


### Security Updates

* Update cURL to 7.59. (DCOS_OSS-2367)

* Updated OpenSSL to 1.0.2n. (DCOS_OSS-1903)

* Mesos does not expose ZooKeeper credentials anymore via its state JSON document. (DCOS_OSS-2162)

* TLS: Admin Router should be configured with both RSA and EC type certificates. (DCOS-22050)

* Disable the 3DES bulk encryption algorithm for Master Admin Router's TLS. (DCOS-21958)

* Disable the TLS 1.1 protocol for Master Admin Router's TLS. (DCOS-22326)


### Notable changes

* Mesos now uses the jemalloc memory profiler by default. (DCOS_OSS-2137)

* Updated DC/OS UI to master+v2.19.4 [Changelog](https://github.com/dcos/dcos-ui/releases/tag/master+v2.19.4)

* Replaced the dcos-diagnostics check runner with dcos-check-runner. (DCOS_OSS-3491)

* Removed the DC/OS web installer. (DCOS_OSS-2256)

* Updated Metronome to 0.5.0. (DCOS_OSS-2338)

* Updated OTP version to 20.3.2 (DCOS_OSS-2378)

* Updated REX-Ray version to 0.11.2 (DCOS_OSS-3597) [rexray v0.11.2](https://github.com/rexray/rexray/releases/tag/v0.11.2)

* DC/OS can now be installed with SELinux in enforcing mode with the "targeted" policy loaded (DCOS-38953)
