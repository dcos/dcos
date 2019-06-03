Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!


## DC/OS 1.12.4 (in development)

### Notable changes

* Updated DC/OS UI to [1.12+v2.26.12](https://github.com/dcos/dcos-ui/releases/tag/1.12+v2.26.12)

* Updated to [Mesos 1.7.3-dev](https://github.com/apache/mesos/blob/0f4e34b4dfe98178a7d94f5242041b5958eb7a24/CHANGELOG).

* Updated to [Metronome 0.6.18](https://github.com/dcos/metronome/blob/e06e8285c089ed7e03590053395f9436a4ac34f4/changelog.md#0618).

* Updated to [Marathon 1.7.216](https://github.com/mesosphere/marathon/tree/9e2a9b579).

* Updated REX-Ray to [version 0.11.4](https://github.com/rexray/rexray/releases/tag/v0.11.4). (DCOS_OSS-4316, COPS-3961)

* Updated ZooKeeper to release [3.4.14](https://zookeeper.apache.org/doc/r3.4.14/releasenotes.html). (DCOS_OSS-5002)

* Introduced a new DC/OS configuration variable `adminrouter_x_frame_options`, defaulting to `SAMEORIGIN`. This can be used for controlling the `X-Frame-Options` HTTP header sent with the DC/OS UI. (DCOS-49594)
* Updated ref of dvdcli to fix dvdcli package build (DCOS-53581)

* Updated urllib3 version to 1.24.2 due to: https://nvd.nist.gov/vuln/detail/CVE-2019-11324. (DCOS-52210)

### Fixed and improved

* `dcos_generate_config[ee].sh --validate-config` doesn't complain about missing deprecated `ssh_*` options anymore. (DCOS_OSS-5152)

* Fixed undecoded framework names in metric tags. (DCOS_OSS-5039)

* Fixed a bug as of which DC/OS checks may accidentally fail, pre-maturely reporting `network is unreachable`. (DCOS-47608)

* Improved Cosmos to handle more transient errors behind the scenes, enhancing its fault tolerance. (DCOS-51139)

* `docker-gc` now removes unused volumes. (DCOS_OSS-1502) CONF

* Fixed a bug in Admin Router's service endpoint as of which the DCOS_SERVICE_REQUEST_BUFFERING setting was not adhered to in all cases. (DCOS_OSS-4999)

* Consolidated Telegraf for workloads that emit a large number of metrics. (DCOS-50994)

* Consolidated Mesos metric collection by tuning timeout constants used in the Telegraf Mesos metric plugin. (DCOS-50672)

* Prefixed illegal Prometheus metric names with an underscore, to enhance compatibility with more metric generators. (COPS-4634, COPS-3067)

* Fixed dcos-net-setup.py failing when systemd network directory did not exist. (DCOS-49711) CONF

* Fixed a race condition in L4LB. (DCOS_OSS-4939)

* [Marathon] Introduced global throttling for Marathon health checks (MARATHON-8596)

* [Marathon] Do not fail on offers with RAW and BLOCK disk types (MARATHON-8590)

* [Marathon] Map `tcp,udp` to `udp,tcp` during migration (MARATHON-8575)

* [Marathon] Allow all users to execute /marathon/bin/marathon (MARATHON-8581)

* [Marathon] Response asynchronously for all endpoints (MARATHON-8562)

* [Marathon] Force expunge and Decommission all instances on service removal (DCOS-49521)

* Conflict between VIP port and port mapping. (DCOS_OSS-4970)

* CNAME records should appear before A/AAAA records. (DCOS_OSS-5108)

* ipset protocol ignores a missing `match` flag on some kernel versions. (DCOS-52780)

* Support large uploads for Admin Router service endpoint. (DCOS-52768)

* Added Round-Robin DNS support. (DCOS_OSS-5118)

### Security updates

* Updated to [OpenSSL 1.0.2r](https://www.openssl.org/news/openssl-1.0.2-notes.html). (DCOS_OSS-4868)

* The configuration parameters `aws_secret_access_key` and `exhibitor_azure_account_key` for exhibitor are now marked as secret and will thus not be revealed in `user.config.yaml` on cluster nodes but will from now on appear only in `user.config.full.yaml` which has stricter read permissions and is not included in DC/OS Diagnostics bundles. (DCOS-51751)

* Made it possible to install and run DC/OS with `/tmp` mounted with `noexec`. (DCOS-53077)


## DC/OS 1.12.3 (2019-03-14)

### Notable changes

### Fixed and improved

* Include additional container metrics if provided (DCOS_OSS-4624)

* Tighten permissions on ZooKeeper directories (DCOS-47687)

* Improve error message in case Docker is not running at start of installation (DCOS-15890)

* Stop requiring `ssh_user` attribute in `config.yaml` when using parts of deprecated CLI installer (DCOS_OSS-4613)

* Telegraf: Fix a bug in the Mesos input plugin that could cause metrics to be mis-tagged (DCOS_OSS-4760)

* Telegraf: Doubled the buffer limit to drop fewer metrics (DCOS-49277)
* Telegraf: Increase the default polling interval to 20s (DCOS-49301)

### Security updates


## DC/OS 1.12.2 (2019-02-11)

### Notable changes

* Expose Public IP (DCOS_OSS-4514)

* Add thisnode.thisdcos.directory dns zone (DCOS_OSS-4666)

### Fixed and improved

* Mark `dcos6` overlay network as disabled if `enable_ipv6` is set to false. (DCOS-40539)

* Expose a Mesos flag to allow the network CNI root directory to be persisted across host reboot. (DCOS_OSS-4667)

* Add config option to enable/disable the Mesos input plugin in Telegraf. (DCOS_OSS-4667)

* Fix CLI task metrics summary command which was occasionally failing to find metrics (DCOS_OSS-4679)

* Make cluster identity configurable in dcos-net (DCOS_OSS-4620)

### Security updates


## DC/OS 1.12.1 (2019-01-03)

### Notable changes

* Run dcos-diagnostics as the `root` user (DCOS_OSS_3877)

* Users can now supply additional Telegraf settings (DCOS-42214)

* Bumped DC/OS UI to [1.12+v2.25.11](https://github.com/dcos/dcos-ui/releases/tag/1.12%2Bv2.25.11)

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

### Security updates

* Update Java to 8u192. (DCOS_OSS-4381)


## DC/OS 1.12.0 (2018-10-25)

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

* Updated DC/OS UI to 1.12+v2.25.10 [Changelog](https://github.com/dcos/dcos-ui/releases/tag/1.12+v2.25.10)

* Updated Metronome to 0.5.0. (DCOS_OSS-2338)

* Updated OTP version to 20.3.2 (DCOS_OSS-2378)

* Updated REX-Ray version to 0.11.2 (DCOS_OSS-3597) [rexray v0.11.2](https://github.com/rexray/rexray/releases/tag/v0.11.2)

### Breaking changes

* Removed the DC/OS web installer. (DCOS_OSS-2256)

* Replaced dcos-metrics with Telegraf. (DCOS_OSS-3714)

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
