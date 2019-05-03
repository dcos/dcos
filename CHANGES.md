Please follow the [`CHANGES.md` modification guidelines](https://github.com/dcos/dcos/wiki/CHANGES.md-guidelines). Thank you!


## DC/OS 1.13.1 (in development)

### Notable changes

* Updated urllib3 version to 1.24.2 due to: https://nvd.nist.gov/vuln/detail/CVE-2019-11324. (DCOS-52210)

### Fixed and improved

* Consolidated diagnostics bundle creation by applying a timeout when reading systemd journal entries. (DCOS_OSS-5097)

* Use gzip compression for some UI assets. (DCOS-5978)

* Fixed a syntax error in cloud fault domain detect script. (DCOS-51792)

### Security updates

* Made it possible to install and run DC/OS with `/tmp` mounted with `noexec`. (DCOS-53077)

## DC/OS 1.13.0

### Highlights

#### Introduction of service accounts, alignment of authentication architectures

The core of the DC/OS Enterprise identity and access management service (IAM) has been open-sourced and added to DC/OS, replacing `dcos-oauth`. CockroachDB was added as a DC/OS component as a highly available database serving the IAM.

With that DC/OS now supports service accounts. Service accounts allow individual tools and applications to interact with a DC/OS cluster using their own identity. A successful service account login results in authentication proof -- the DC/OS authentication token. A valid DC/OS authentication token is required in order to access DC/OS services and components through Master Admin Router.

This change also aligned the authentication architectures between DC/OS Enterprise and DC/OS: the HTTP API for service account management as well as for service account login is now the same in both systems. The DC/OS authentication token implementation details are equivalent in both systems: it is a JSON Web Token (JWT) of type RS256 which can be validated by any component in the system after consulting the IAM's JSON Web Key Set (JWKS) endpoint.

#### DC/OS metrics overhaul

Metrics for the following DC/OS components are now collected: CockroachDB, ZooKeeper, Exhibitor, Root Marathon, Metronome, Admin Router.

* Admin Router Nginx Virtual Hosts metrics are now collected by default. An Nginx instance metrics display is available on `/nginx/status` on each DC/OS master node. (DCOS_OSS-4562)

* Mesos metrics are now available by default. (DCOS_OSS-3815)

* Metrics are tagged with their fault domain region and zone. (DCOS-16570)

* Telegraf's statsd input plugin reports additional internal metrics. (DCOS_OSS-4759)

* Prometheus-format metrics can be gathered from tasks (DCOS_OSS-3717)

* Expose internal metrics for the Telegraf metrics pipeline (DCOS_OSS-4608)

* Add Metrics for dns forwarding (DCOS-48336)

* Add metrics for lashup (DCOS_OSS-4756)

* Enable metrics for fluent-bit (DCOS-51855)

* Add basic support for prometheus to dcos-net (DCOS_OSS-4738)



### Known limitations

* Authentication tokens emitted by `dcos-oauth` prior to an upgrade from DC/OS version 1.12.x to DC/OS version 1.13.x will become invalid during the upgrade. Simply log in again.

### Breaking changes

### What's new

* Introduced the `dcos-ui-update-service`, this component exposes an API to update the servered `dcos-ui` version using the `dcos-ui` package published to Universe.

* Release of Marathon 1.8 adds ability to launch App or Pod containers defined with a seccomp profile.

* Release of Marathon 1.8 with refactored Task Instance management.

* Telegraf's statsd input plugin reports additional internal metrics. (DCOS_OSS-4759)

* Telegraf's procstat input plugin reports process metrics (DCOS-50778).

* Bumped DC/OS UI to [master+v2.40.10](https://github.com/dcos/dcos-ui/releases/tag/master%2Bv2.40.10)

* Marathon and Metronome have DC/OS install flag to configure GPU support.  "restricted", "unrestricted", "undefined" and "" are valid.

* Metronome supports UCR.

* Metronome supports file-based secrets.

* Metronome supports hybrid cloud.

* Add thisnode.thisdcos.directory dns zone (DCOS_OSS-4666)

* Make cluster identity configurable in dcos-net (DCOS_OSS-4620)

* Expose a Mesos flag to allow the network CNI root directory to be persisted across host reboot (DCOS_OSS-4667)

* Allow setting environment variables for `docker-gc` in `/var/lib/dcos/docker-gc.env`

* Admin Router returns relative redirects to avoid relying on the Host header (DCOS-47845)

* Master Admin Router: the service endpoint at `/service/<service-name>` does not strip the `Accept-Encoding` header anymore from requests, allowing services co serve compressed responses to user agents. (DCOS_OSS-4906)

* DC/OS Net: OTP has been upgraded to version 21.3. (DCOS_OSS-4902)


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
