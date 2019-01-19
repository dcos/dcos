## DC/OS 1.12-dev

### Notable changes

### Breaking changes

### Fixed and improved

* Mark `dcos6` overlay network as disabled if `enable_ipv6` is set to false (DCOS-40539)

* Expose a Mesos flag to allow the network CNI root directory to be persisted across host reboot. (DCOS_OSS-4667)

* Add config option to enable/disable the Mesos input plugin in Telegraf. (DCOS_OSS-4667)

* Fix CLI task metrics summary command which was occasionally failing to find metrics (DCOS_OSS-4679)

### Security Updates

## DC/OS 1.12.1

### Notable changes

* Run dcos-diagnostics as the `root` user (DCOS_OSS_3877)

* Users can now supply additional Telegraf settings (DCOS-42214)

* Bumped DC/OS UI to [1.12+v2.25.11](https://github.com/dcos/dcos-ui/releases/tag/1.12%2Bv2.25.11)

### Breaking changes

### Fixed and improved

* Docker-GC will now log to journald. (COPS-4044)

* dcos-net ignores some tcp/udp discovery ports for tasks on host network (DCOS_OSS-4395)

* Minuteman routes traffic until the first failed health check (DCOS_OSS-1954)

* dcos-net continously restarting systemd-networkd on a bare-metal server with bond interfaces (DCOS_OSS-4398)

* Lots of CRASH messages in dcos-net logs (DCOS-45161)

* Telegraf: Added configurable whitelists for labels to include in metrics (DCOS-43591)

* Make push_ops_timeout configurable through config.yaml (DCOS-45196)

* Metrics now include executor container information. (DCOS_OSS-4181)

* Docker container unable to curl its own VIP (DCOS-45115)

* Make cluster identity configurable in dcos-net (DCOS_OSS-4620)

* Number of concurrent subscribers to Mesos master operator API is now capped to 1000 by default, with a Mesos master flag to configure (DCOS_OSS-4164)

### Security Updates

* Update Java to 8u192. (DCOS_OSS-4381)


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

* Fixed race condition in Telegraf dcos_statsd input plugin. (DCOS_OSS-4096)

* Check system clock is synced before starting Exhibitor (DCOS_OSS-4287)

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

* Marathon framework ID generation is now very conservative. [See more](https://github.com/mesosphere/marathon/blob/master/changelog.md#marathon-framework-id-generation-is-now-very-conservative) (MARATHON-8420)


### Security Updates

* Mark `dcos6` overlay network as disabled if `enable_ipv6` is set to false (DCOS-40539)

### Notable changes

* Updated DC/OS UI to 1.12+v2.25.10 [Changelog](https://github.com/dcos/dcos-ui/releases/tag/1.12+v2.25.10)

* Updated Metronome to 0.5.0. (DCOS_OSS-2338)

* Updated OTP version to 20.3.2 (DCOS_OSS-2378)

* Updated REX-Ray version to 0.11.2 (DCOS_OSS-3597) [rexray v0.11.2](https://github.com/rexray/rexray/releases/tag/v0.11.2)
