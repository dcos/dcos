Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!

## DC/OS 1.13.2 (in development)


### Notable changes

* Updated to [Metronome 0.6.23](https://github.com/dcos/metronome/tree/be50099).

### Fixed and improved

* Mesos task logs are sent to Fluent Bit with task metadata included. (DCOS-53834)

* Telegraf reports procstat metrics only for DC/OS systemd services, instead of all processes. (DCOS-53589)

* [Metronome] Missing request metrics in Metronome. (DCOS_OSS-5020)

* [Metronome] Improve secrets validation to only point out unprovided secrets. (DCOS_OSS-5019)

### Security updates


## DC/OS 1.13.1

### Notable changes

* ZooKeeper instances on master nodes can now be backed up and restored via a dedicated command line script `dcos-zk` that is shipped with DC/OS. (DCOS_OSS-5186)

* Bumped DC/OS UI to [1.13+v2.82.3](https://github.com/dcos/dcos-ui/releases/tag/1.13+v2.82.3)

### Fixed and improved

* Added Fluent Bit metrics to the pipeline (DCOS-54425)

* Fixed Telegraf configuration error that dropped task metrics with certain names or tags. (DCOS_OSS-5032)

* `dcos_generate_config[ee].sh --validate-config` doesn't complain about missing deprecated `ssh_*` options anymore. (DCOS_OSS-5152)

* Fixed undecoded framework names in metric tags. (DCOS_OSS-5039)

* Consolidated diagnostics bundle creation by applying a timeout when reading systemd journal entries. (DCOS_OSS-5097)

* Admin Router: allow for gzip compression when serving some UI assets. (DCOS-5978)

* Fixed a syntax error in cloud fault domain detect script. (DCOS-51792)

* Fixed a number of issues that caused some DC/OS components to crash when `/tmp` is mounted with the `noexec` option. (DCOS-53077)

* Support large uploads for Admin Router service endpoint. (DCOS-52768)

* Added Round-Robin DNS support. (DCOS_OSS-5118)

* [Marathon] Fix restarting resident apps and pods. (DCOS_OSS-5212)

* [Marathon] Only match disk with profile if that profile is needed. (DCOS_OSS-5211)

* [Marathon] Better handle invalid state command exceptions in InstanceTrackerActor. (MARATHON-8623)

* [Marathon] Add TASK_UNKNOWN to the valid mesos task status enums. (MARATHON-8624)

* [Marathon] Prevent a rare but benign NPE when a deployment is canceled. (MARATHON-8616)

* [Marathon] Prevent instance leak. (DCOS-51375)

* [Marathon] Introduce new exit error code when the framework was removed from Mesos.

* Ensure Bouncer uses configured web proxy. (DCOS_OSS-5167)


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
