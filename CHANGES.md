Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!

## DC/OS 1.13.4 (In Development)

### Notable changes

* Updated DC/OS UI to [1.13+v2.82.9](https://github.com/dcos/dcos-ui/releases/tag/1.13+v2.82.9).

* Updated to [Mesos 1.8.x](https://github.com/apache/mesos/blob/6ecaa5106ffd5b2f712854e97b5386741b1d14a7/CHANGELOG)

* Marathon Updated to 1.8.222 (DCOS_OSS-5460)

### Fixed and improved

* Fix preflight docker version check failing for docker 1.19. (DCOS-56831)

* The content of `/var/log/mesos-state.tar.gz` is now included in the diagnostics bundle. (DCOS-56403)

* Prune VIPs with no backends in order to avoid unbounded growth of state and messages exchanged among `dcos-net` processes. (DCOS_OSS-5356)

* [Marathon] Clarify support for ranges and sets with constraint operators (MARATHON-7977)

* [Marathon] Revive and suppress offers based on instance state (MARATHON-8627)

* [Marathon] Exit with 111 if Marathon could not bind to address (MARATHON-8685)

* [Marathon] Added maintenance mode to info endpoint (MARATHON-8660)

* [Marathon] Remove strict validation of external volume name (MARATHON-8681)

* DC/OS Net: Fix support for big sets in the ipset manager. (COPS-5229)

### Security updates

## DC/OS 1.13.3 (CF - 2019-07-10)

### Notable changes

* Updated to [Metronome 0.6.33](https://github.com/dcos/metronome/releases/tag/v0.6.33)

* Updated to [Marathon 1.8.207](https://github.com/mesosphere/marathon/tree/9f3550487).

* Updated to [Mesos 1.8.x](https://github.com/apache/mesos/blob/07d053f68b75505a4386913f05d521fa5e36373d/CHANGELOG)

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

* Updated DC/OS UI to [1.13+v2.82.6](https://github.com/dcos/dcos-ui/releases/tag/1.13+v2.82.6)

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


## DC/OS 1.13.1 (2019-05-31)

### Notable changes

* Updated to [Mesos 1.8.1-dev](https://github.com/apache/mesos/blob/f5770dcf322bd8a88e6c88041364a4089d92be90/CHANGELOG).

* Updated DC/OS UI to [1.13+v2.82.3](https://github.com/dcos/dcos-ui/releases/tag/1.13+v2.82.3)

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
