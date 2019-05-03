Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!


## DC/OS 1.13.1 (in development)

### Notable changes

### Fixed and improved

* Consolidated diagnostics bundle creation by applying a timeout when reading systemd journal entries. (DCOS_OSS-5097)

* Admin Router: allow for gzip compression when serving some UI assets. (DCOS-5978)

* Fixed a syntax error in cloud fault domain detect script. (DCOS-51792)

### Security updates

* Made it possible to install and run DC/OS with `/tmp` mounted with `noexec`. (DCOS-53077)
* Updated urllib3 to version 1.24.2, for addressing [CVE-2019-11324](https://nvd.nist.gov/vuln/detail/CVE-2019-11324). (DCOS-52210)


## DC/OS 1.13.0

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

### What's new

* Introduced the `dcos-ui-update-service`. This component exposes an API which allows for updating the `dcos-ui` from the DC/OS Universe.

* Marathon 1.8 is now included. Among others, it adds the ability to launch app or pod containers defined with a seccomp profile.

* Updated the DC/OS UI to version [master+v2.40.10](https://github.com/dcos/dcos-ui/releases/tag/master%2Bv2.40.10).

* Introduced two new DC/OS configuration options, `metronome_gpu_scheduling_behavior`, and `marathon_gpu_scheduling_behavior`. By default, their values are set to `restricted`.

* Metronome supports the universal containerizer (UCR), as well as the "file-based secrets", and "hybrid cloud" DC/OS capabilities.

* Add thisnode.thisdcos.directory dns zone (DCOS_OSS-4666)

* Make cluster identity configurable in dcos-net (DCOS_OSS-4620)

* Expose a Mesos flag to allow the network CNI root directory to be persisted across host reboot (DCOS_OSS-4667)

* Allow setting environment variables for `docker-gc` in `/var/lib/dcos/docker-gc.env`

* Admin Router returns relative redirects to avoid relying on the Host header (DCOS-47845)

* Master Admin Router: the service endpoint at `/service/<service-name>` does not strip the `Accept-Encoding` header anymore from requests, allowing services co serve compressed responses to user agents. (DCOS_OSS-4906)

* DC/OS Net: OTP has been upgraded to version 21.3. (DCOS_OSS-4902)

* Admin Router now collects so-called virtual host metrics, for fine-grained monitoring. Each Admin Router instance exposes a summary on `/nginx/status`. (DCOS_OSS-4562)

* Mesos metrics are now available by default. (DCOS_OSS-3815)

* Metrics are tagged with their fault domain region and zone. (DCOS-16570)

* Internal metrics for the Telegraf-based metrics pipeline are now exposed. (DCOS_OSS-4608)

* Telegraf's statsd input plugin reports additional internal metrics. (DCOS_OSS-4759)

* Telegraf's procstat input plugin reports process metrics (DCOS-50778).

### Fixed and improved

Note(JP): most of the points below need to be filtered out (contained in previous 1.12.x point releases).


* Fixed issue where Metronome did not handle restart policy is ON_FAILURE correctly, not restarting the task. (DCOS_OSS-4636 )

* Telegraf is upgraded to 1.9.4. (DCOS_OSS-4675)

* Allow the DC/OS installer to be used when there is a space in its path (DCOS_OSS-4429).

* Admin Router logs to non-blocking socket. (DCOS-43956)

* Add path-based routing to AR to routing requests to `dcos-net` (DCOS_OSS-1837)

* Fix CLI task metrics summary command which was occasionally failing to find metrics (DCOS_OSS-4679)

* Add a warning to the installer to let the user know if case kernel modules required by DSS are not loaded (DCOS-49088)

* Enable ipv6 support for l4lb by default (DCOS_OSS-1993)

* HTTP endpoint targets of DC/OS Diagnostics can be marked optional (DCOS_OSS-5031)


* Lashup sometime fails to converge (DCOS_OSS-4328)
