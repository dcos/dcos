Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/blob/master/CHANGES-guidelines.md). Thank you!

## DC/OS 1.13.10 (in development)

### Security updates

* Updated CockroachDB Python package to 0.3.5. (D2IQ-62221) 

### Notable changes

* Starting services on clusters with static masters now only requires a majority of ZooKeeper nodes to be available. 
  Previously, all ZooKeeper nodes needed to be available.
  On clusters with dynamic master lists, all ZooKeeper nodes must still be available. (D2IQ-4248)
  
### Fixed and improved

* Removed trailing newline from ZooKeeper log messages. (D2IQ-68394)

* Updated DC/OS UI to [v5.1.7](https://github.com/dcos/dcos-ui/releases/tag/v5.1.7).

* Fix incorrect ownership after migration of `/run/dcos/telegraf/dcos_statsd/containers`. (D2IQ-69295)

* Update Telegraf configuration to reduce errors, vary requests to reduce load, sample less frequently. (COPS-5629)

* Display user email address in UI when logging in using external provider. (D2IQ-70199)

* Removed Exhibitor snapshot cleanup and now rely on ZooKeeper autopurge. (D2IQ-68109)


#### Update Metronome to 0.6.48

* Fix an issue in Metronome where it became unresponsive when lots of pending jobs existed during boot. (DCOS_OSS-5965)

* There was a case where regex validation of project ids was ineffecient for certain inputs. The regex has been optimized. (MARATHON-8730)

* Metronome jobs networking is now configurable (MARATHON-8727)

#### Update Marathon to 1.8.244

* Fix a regression where Marathon would sometimes fail to replace lost unreachable tasks (MARATHON-8758)

* Improved the reliability of error handling for health check handling (MARATHON-8743)

## DC/OS 1.13.9 (2020-4-22)

### Notable changes

### Fixed and improved

* Updated DC/OS UI to [v4.0.1](https://github.com/dcos/dcos-ui/releases/tag/v4.0.1).

* Marathon updated to 1.8.242

* Marathon was checking authorization for unrelated apps when performing a kill-and-scale operations; this has been resolved. (MARATHON-8731)

* Update to Fluentbit [1.4.6](https://docs.fluentbit.io/manual/installation/upgrade-notes)


### Security updates

* Update to OpenSSL 1.0.2u. (D2IQ-66526)


## DC/OS 1.13.8 (2020-02-27)

### Notable changes

* Updated to Mesos [1.8.2-dev](https://github.com/apache/mesos/blob/bb32bf8732af3e941aa651c82f5c4f3f03e2e139/CHANGELOG)

### Fixed and improved

* Marathon: Pod status reports would miss tasks in state `TASK_UNKOWN` (MARATHON-8710)

* Fixed preflight check verifying the `ftype` value of /var/lib/mesos. (DCOS-59406)

* Allow Admin Router to accept files up to 32GB, such as for uploading large packages to Package Registry. (DCOS-61233)

* DC/OS no longer increases the rate limit for journald logging.  Scale testing demonstrated that raising the limit overloads journald, causing problems for other components that see delayed or lost logs or, worse, hang until log buffers are read. The default of 10000 messages per 30 seconds appears to distinguish well between busy components and excessively verbose components. (DCOS-53763)

* Fix Telegraf migration when no containers present. (D2IQ-64507)

* Marathon version bumped to 1.8.239

    * /v2/tasks plaintext output in Marathon 1.5 returned container network endpoints in an unusable way (MARATHON-8721)
    * Unreachable instances would interfere with replacements when using GROUP_BY / UNIQUE placement constraints, even if expungeAfter is configured the same as inactiveAfter (MARATHON-8719)

* Adjust dcos-net (l4lb) to allow for graceful shutdown of connections by changing the VIP backend weight to `0`
  when tasks are unhealthy or enter the `TASK_KILLING` state instead of removing them. (D2IQ-61077)

### Security updates


## DC/OS 1.13.7 (2019-12-19)

### Notable changes

* Updated DC/OS UI to [1.13+v2.83.3](https://github.com/dcos/dcos-ui/releases/tag/1.13+v2.83.3).

* Update Marathon to [1.8.232](https://github.com/mesosphere/marathon/commit/d3517aee0dfe495e2bdce34bdfc0e6f10345371b)


### Fixed and improved

* DC/OS overlay networks should be compared by-value. (DCOS_OSS-5620)

* Drop labels from Lashup's kv_message_queue_overflows_total metric. (DCOS_OSS-5634)

* Reserve all agent VTEP IPs upon recovering from replicated log. (DCOS_OSS-5626)

* Use Golang 1.10.8 to build CockroachDB. (DCOS-61502)
* [Mesos] Support quoted realms in WWW-Authenticate header (DCOS-61529)


## DC/OS 1.13.6

### Notable changes

* Updated DC/OS UI to [1.13+v2.83.1](https://github.com/dcos/dcos-ui/releases/tag/1.13+v2.83.1).

* Signal now sends telemetry data every 5 minutes instead of every hour. This is to align the frequency with DC/OS Enterprise.

* Updated to Mesos [1.8.2-dev](https://github.com/apache/mesos/blob/c7c716dbc9ee4363ba6267591585b9984d8920b8/CHANGELOG)


### Fixed and improved

* Remove nogroup group creation (COPS-5220)

* Increase number of diagnostics fetchers (DCOS-51483)

* Delete each VTEP IP address only once when deleting agent records (DCOS_OSS-5597)

* Marathon pod instances are now included in the DC/OS diagnostic bundle (DCOS_OSS-5616)

* [Marathon] Very-large Mesos TaskStatus updates no longer  cause Marathon to crash loop (MARATHON-8698)


## DC/OS 1.13.5

### Notable changes

* Updated to [Mesos 1.8.2-dev](https://github.com/apache/mesos/blob/adc958f553c3728aab5529de56b0ddc30c0f9b68/CHANGELOG).

* Updated to Marathon 1.8.227.

### Fixed and improved

* Mesos overlay networking: added an HTTP endpoint for dropping agents from the state. (DCOS_OSS-5536)

* Diagnostics bundle: Fixed a bug as of which the bundle creation job duration was shown as ever-increasing, even after the job finished. (DCOS_OSS-5494)

* Diagnostics bundle: added a REST API with performance improvements. (DCOS_OSS-5098)

* Admin Router: Improved service routing robustness by omitting Marathon apps with wrongly specified DCOS_SERVICE_PORT_INDEX values. (DCOS_OSS-5491)

* [Metronome] Post-install configuration can now be added to `/var/lib/dcos/metronome/environment`. (DCOS_OSS-5509)

* [Marathon] Fixed a bug in which a service could get stuck if a failure occurred while Mesos tried to create a reservation. (MARATHON-8693)

* [Marathon] Strict volume name validation was not relaxed enough in DC/OS release 1.13.4; this has been resolved. (MARATHON-8697)

### Security updates

N/A


## DC/OS 1.13.4 (2019-09-05)

### Notable changes

* Updated DC/OS UI to [1.13+v2.82.9](https://github.com/dcos/dcos-ui/releases/tag/1.13+v2.82.9).

* Updated to [Mesos 1.8.x](https://github.com/apache/mesos/blob/6ecaa5106ffd5b2f712854e97b5386741b1d14a7/CHANGELOG).

* Updated to Marathon 1.8.222. (DCOS_OSS-5460)

### Fixed and improved

* Fixed preflight check for Docker version failing for Docker 1.19. (DCOS-56831)

* The content of `/var/log/mesos-state.tar.gz` is now included in the diagnostics bundle. (DCOS-56403)

* DC/OS Net: Fix support for big sets in the ipset manager. (COPS-5229)

* DC/OS Net: Prune VIPs with no backends in order to avoid unbounded growth of state and messages exchanged among `dcos-net` processes. (DCOS_OSS-5356)

* [Marathon] Clarify support for ranges and sets with constraint operators. (MARATHON-7977)

* [Marathon] Revive and suppress offers based on instance state. (MARATHON-8627)

* [Marathon] Exit with status 111 if Marathon could not bind to address. (MARATHON-8685)

* [Marathon] Added maintenance mode to info endpoint. (MARATHON-8660)

* [Marathon] Removed strict validation of external volume name. (MARATHON-8681)

### Security updates

N/A


## DC/OS 1.13.3 (2019-07-24)

### Notable changes

* Updated to [Metronome 0.6.33](https://github.com/dcos/metronome/releases/tag/v0.6.33).

* Updated to [Marathon 1.8.207](https://github.com/mesosphere/marathon/tree/9f3550487).

* Updated to [Mesos 1.8.x](https://github.com/apache/mesos/blob/07d053f68b75505a4386913f05d521fa5e36373d/CHANGELOG).

* Updated the DC/OS UI to version [1.13+v2.82.7](https://github.com/dcos/dcos-ui/releases/tag/1.13+v2.82.7).

* Updated the DC/OS Signal service to release [1.6.0](https://github.com/dcos/dcos-signal/commits/1.6.0).

### Fixed and improved

* Consolidated `iam-database-restore` to work when no database exists. This helps recovery in rare scenarios. (DCOS_OSS-5317)

* Consolidated `dcos-zk backup` and `dcos-zk restore` to exit early with a clear error message if ZooKeeper is still running. (DCOS_OSS-5353)

* DC/OS Metrics: Prometheus metrics can now be collected from Mesos tasks in the `container` networking mode. (DCOS-56018, COPS-5040)

* DC/OS Checks: made false negative results less likely by changing a timeout constant. (DCOS-53742, COPS-5041)

* [Marathon] Marathon will not get stuck anymore when trying to kill an unreachable instance. (MARATHON-8422)

* [Marathon] Persistent volumes tagged with a profile name now default to `DiskType.Mount`. (MARATHON-8631)

### Security updates

N/A


## DC/OS 1.13.2 (2019-07-03)

## Notable changes

* Updated to [Mesos 1.8.1-dev](https://github.com/apache/mesos/blob/fca89344aff96a8e2ec1b5b70f4a3cb0e899c352/CHANGELOG).

* Updated to [Metronome 0.6.27](https://github.com/dcos/metronome/tree/b8a73dd).

* Updated to [Marathon 1.8.204](https://github.com/mesosphere/marathon/tree/5209e3183).

* Updated DC/OS UI to [1.13+v2.82.6](https://github.com/dcos/dcos-ui/releases/tag/1.13+v2.82.6).

* ZooKeeper instances on master nodes can now be backed up and restored via a dedicated command line script `dcos-zk` that is shipped with DC/OS. (DCOS_OSS-5186)

### Fixed and improved

* Mesos task logs are now sent to Fluent Bit with task metadata included. (DCOS-53834)

* Telegraf reports procstat metrics only for DC/OS systemd services, instead of all processes. (DCOS-53589)

* Telegraf now supports specyfying port names for task-label based Prometheus endpoints discovery. (DCOS-55100)

* Fixed Telegraf configuration error that dropped task metrics with certain names or tags. (DCOS_OSS-5032)

* Added Fluent Bit metrics to the pipeline. (DCOS-54425)

* [Metronome] Improved validation of secrets. (DCOS_OSS-5019)

* [Metronome] The task ID is now included in finished job runs. (DCOS_OSS-5273)

* [Marathon ] Fixed an issue where two independent deployments could interfere with each other resulting in too many tasks launched and/or possibly a stuck deployment. (DCOS-54927, DCOS_OSS-5260)

* [Cosmos] Consolidated fetching artifacts from the Internet. (DCOS-54077)

* [Cosmos] Restored old behavior of the `describe` command. (DCOS-44111)

### Security updates

N/A


## DC/OS 1.13.1 (2019-05-31)

### Notable changes

* Updated to [Mesos 1.8.1-dev](https://github.com/apache/mesos/blob/f5770dcf322bd8a88e6c88041364a4089d92be90/CHANGELOG).

* Updated DC/OS UI to [1.13+v2.82.3](https://github.com/dcos/dcos-ui/releases/tag/1.13+v2.82.3).

### Fixed and improved

* DC/OS Net: consolidated writing `resolv.conf`, addressing a rare race condition. (DCOS-47608)

* `dcos_generate_config[ee].sh --validate-config` doesn't complain about missing deprecated `ssh_*` options anymore. (DCOS_OSS-5152)

* Fixed undecoded framework names in metric tags. (DCOS_OSS-5039)

* Consolidated diagnostics bundle creation by applying a timeout when reading systemd journal entries. (DCOS_OSS-5097)

* Admin Router: allow for gzip compression when serving some UI assets. (DCOS-5978)

* Fixed a syntax error in cloud fault domain detect script. (DCOS-51792)

* Fixed a number of issues that caused some DC/OS components to crash when `/tmp` is mounted with the `noexec` option. (DCOS-53077)

* Support large uploads for Admin Router service endpoint. (DCOS-52768, COPS-4651)

* Added Round-Robin DNS support. (DCOS_OSS-5118)

* Ensure the DC/OS IAM (Bouncer) uses the configured web proxy details. (DCOS_OSS-5167)

* [Marathon] Fix restarting resident apps and pods. (DCOS_OSS-5212)

* [Marathon] Only match disk with profile if that profile is needed. (DCOS_OSS-5211)

* [Marathon] Better handle invalid state command exceptions in InstanceTrackerActor. (MARATHON-8623)

* [Marathon] Add TASK_UNKNOWN to the valid mesos task status enums. (MARATHON-8624)

* [Marathon] Prevent a rare but benign NPE when a deployment is canceled. (MARATHON-8616)

* [Marathon] Prevent instance leak. (DCOS-51375)

* [Marathon] Introduce new exit error code when the framework was removed from Mesos.

### Security updates

* Updated urllib3 to version 1.24.2, for addressing [CVE-2019-11324](https://nvd.nist.gov/vuln/detail/CVE-2019-11324). (DCOS-52210)


## DC/OS 1.13.0 (2019-05-13)

### Highlights

#### Introduction of service accounts, alignment of authentication architectures

The core of the DC/OS Enterprise identity and access management service (IAM) has been open-sourced and added to DC/OS, replacing `dcos-oauth`. CockroachDB was added as a DC/OS component as a highly available database serving the IAM.

With that DC/OS now supports service accounts. Service accounts allow individual tools and applications to interact with a DC/OS cluster using their own identity. A successful service account login results in authentication proof -- the DC/OS authentication token. A valid DC/OS authentication token is required in order to access DC/OS services and components through Master Admin Router.

This change also aligned the authentication architectures between DC/OS Enterprise and DC/OS: the HTTP API for service account management as well as for service account login is now the same in both systems. The DC/OS authentication token implementation details are equivalent in both systems: it is a JSON Web Token (JWT) of type RS256 which can be validated by any component in the system after consulting the IAM's JSON Web Key Set (JWKS) endpoint.

#### DC/OS monitoring overhaul

Most DC/OS components (Admin Router, CockroachDB, ZooKeeper, Exhibitor, Root Marathon, Metronome, Spartan, Lashup, and others) now emit more useful metrics into the DC/OS metrics pipeline than before.

The new `DC/OS monitoring service` can be deployed from the DC/OS Universe. It consumes the metrics emitted by DC/OS components and workloads, feeds them into a time series database and provides a curated set of Grafana dashboards for a holistic DC/OS monitoring approach.

### Known limitations

* Authentication tokens emitted by `dcos-oauth` prior to an upgrade from DC/OS version 1.12.x to DC/OS version 1.13.x will become invalid during the upgrade. Simply log in again.

### Breaking changes

No breaking changes are known to date.

### What's new

* Introduced the `dcos-ui-update-service`. This component exposes an API which allows for updating the `dcos-ui` from the DC/OS Universe. In this release, the default DC/OS UI was updated to version [master+v2.40.10](https://github.com/dcos/dcos-ui/releases/tag/master%2Bv2.40.10).

* Marathon 1.8 is now included. Among others, it adds the ability to launch app or pod containers defined with a seccomp profile.

* Introduced the DC/OS configuration options `metronome_gpu_scheduling_behavior` and `marathon_gpu_scheduling_behavior`. By default, their values are set to `restricted`.

* Metronome now supports the universal containerizer (UCR), as well as the "file-based secrets", and "hybrid cloud" DC/OS capabilities.

* Environment variables can now be set for `docker-gc` in `/var/lib/dcos/docker-gc.env`. (DCOS_OSS-1140)

* Master Admin Router: the service endpoint at `/service/<service-name>` does not strip the `Accept-Encoding` header anymore from requests, allowing services to serve compressed responses to user agents. (DCOS_OSS-4906)

* Admin Router now returns relative redirects to avoid relying on the Host header. (DCOS-47845)

* Admin Router now collects so-called virtual host metrics, for fine-grained monitoring. Each Admin Router instance exposes a summary at `/nginx/status`. (DCOS_OSS-4562)

* Admin Router now logs to a non-blocking Unix domain socket. If `journald` fails to read the socket quickly enough, log messages may be lost. Before, Admin Router hang in this case (stopping to process requests). (DCOS-43956)

* Master Admin Router now exposes the DC/OS Net API via `/net`. This can be used, for example, for reading the public IP addresses of public agent nodes (`/net/v1/nodes`). (DCOS_OSS-1837)

* DC/OS Net: ipv6 support is now enabled in L4LB by default. (DCOS_OSS-1993)

* DC/OS Net: OTP has been upgraded to version 21.3. (DCOS_OSS-4902)

* Mesos metrics are now available by default. (DCOS_OSS-3815)

* Metrics are tagged with their fault domain region and zone. (DCOS-16570)

* Internal metrics for the Telegraf-based metrics pipeline are now exposed. (DCOS_OSS-4608)

* Telegraf's statsd input plugin reports additional internal metrics. (DCOS_OSS-4759)

* Telegraf's procstat input plugin reports process metrics. (DCOS-50778)

* Telegraf has been upgraded to 1.9.4. (DCOS_OSS-4675)

* Allow the DC/OS installer to be used when there is a space in its path. (DCOS_OSS-4429)

* Added a warning to the installer to let the user know in case kernel modules required by the DC/OS storage service are not loaded. (DCOS-49088)

* Set network interfaces as unmanaged for networkd only on coreos. (DCOS-60956)
