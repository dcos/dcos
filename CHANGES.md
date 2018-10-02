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

### What's new

* Replaced the dcos-diagnostics check runner with dcos-check-runner. (DCOS_OSS-3491)

* Mesos now uses the jemalloc memory profiler by default. (DCOS_OSS-2137)

* DC/OS can now be installed with SELinux in enforcing mode with the "targeted" policy loaded. (DCOS-38953)

* Changed the Admin Router access log format for facilitating debugging and performance analysis. (DCOS_OSS-4129)

* Enabled Windows-based pkgpanda builds. (DCOS_OSS-1899)

* DC/OS Net: Support Mesos Windows Agent (DCOS_OSS-2073)

* DC/OS Net: Use Operator HTTP API (DCOS_OSS-1566)

* Admin Router: It is now possible to disable HTTP request buffering for `/service/` endpoint requests through the DCOS_SERVICE_REQUEST_BUFFERING Marathon label. (DCOS_OSS-2420)

* Admin Router: It is now possible to disable upstream request URL rewriting for `/service/` endpoint requests through the DCOS_SERVICE_REWRITE_REQUEST_URLS Marathon label. (DCOS_OSS-2420)

* Added a DC/OS API endpoint to distinguish the 'open' and 'enterprise' build variants. (DCOS_OSS-2283)


### Breaking changes

* Removed the DC/OS web installer. (DCOS_OSS-2256)

* Replaced dcos-metrics with Telegraf (DCOS_OSS-3714)


### Fixed and improved

* Allow dcos-diagnostics bundles location to be configured (DCOS_OSS-4040)

* Add mountinfo to diagnostics bundle (DCOS_OSS_3961)

* Fixed Docker isolation iptables rule reversal on reboot. (DCOS_OSS-3697)

* Updated CNI plugins to v0.7.1. (DCOS_OSS-3841)

* Mesos: Expose memory profiling endpoints. (DCOS_OSS-2137)

* Added an API for checks at /system/checks/ on all cluster nodes. (DCOS_OSS-1406)

* Node and cluster checks are executed in parallel. (DCOS_OSS-2239)

* DC/OS Metrics: moved the prometheus producer from port 9273 to port 61091. (DCOS_OSS-2368)

* Release cosmos v0.6.0. (DCOS_OSS-2195)

* A cluster's IP detect script may be changed with a config upgrade (DCOS_OSS-2389)

* Fixed ftype=1 check for dcos-docker (DCOS_OSS-3549)

* Root Marathon support for post-installation configuration of flags and JVM settings has been improved. (DCOS_OSS-3556)

* Root Marathon heap size can be customized during installation. (DCOS_OSS-3556)

* Fix logging of dcos-checks-poststart results to the journal. (DCOS_OSS-3804)

* Get timestamp on dmesg, timedatectl, distro version, systemd unit status and pods endpoint in diagnostics bundle. (DCOS_OSS-3861)

* DC/OS Net: Logging improvements (DCOS_OSS-3929)

* DC/OS Net: Get rid of epmd (DCOS_OSS-1751)

* Upgrade OTP version (DCOS_OSS-3655)

### Security Updates


### Notable changes

* Updated DC/OS UI to master+v2.24.4 [Changelog](https://github.com/dcos/dcos-ui/releases/tag/master+v2.24.4)

* Updated Metronome to 0.5.0. (DCOS_OSS-2338)

* Updated OTP version to 20.3.2 (DCOS_OSS-2378)

* Updated REX-Ray version to 0.11.2 (DCOS_OSS-3597) [rexray v0.11.2](https://github.com/rexray/rexray/releases/tag/v0.11.2)
