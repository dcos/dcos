## DC/OS 1.13.0

### Highlights

#### Introduction of service accounts, alignment of authentication architectures

The core of the DC/OS Enterprise identity and access management service (IAM) has been open-sourced and added to DC/OS, replacing `dcos-oauth`. CockroachDB was added as a DC/OS component as a highly available database serving the IAM.

With that DC/OS now supports service accounts. Service accounts allow individual tools and applications to interact with a DC/OS cluster using their own identity. A successful service account login results in authentication proof -- the DC/OS authentication token. A valid DC/OS authentication token is required in order to access DC/OS services and components through Master Admin Router.

This change also aligned the authentication architectures between DC/OS Enterprise and DC/OS: the HTTP API for service account management as well as for service account login is now the same in both systems. The DC/OS authentication token implementation details are equivalent in both systems: it is a JSON Web Token (JWT) of type RS256 which can be validated by any component in the system after consulting the IAM's JSON Web Key Set (JWKS) endpoint.


### What's new

* Admin Router Nginx Virtual Hosts metrics are now collected by default. An Ningx instance metrics display is available on `/nginx/status` on each DC/OS master node. (DCOS_OSS-4562)

* CockroachDB metrics are now collected by Telegraf (DCOS_OSS-4529).

* ZooKeeper metrics are now collected by Telegraf (DCOS_OSS-4477).

* Mesos metrics are now available by default. (DCOS_OSS-3815)
* Metronome supports UCR
* Metronome supports file based secrets
* Metronome supports hybrid cloud

* Expose Public IP (DCOS_OSS-4514)

### Breaking changes


### Known limitations

* Authentication tokens emitted by `dcos-oauth` prior to an upgrade from DC/OS version 1.12.x to DC/OS version 1.13.x will become invalid during the upgrade. Simply log in again.


### Fixed and improved

* Add SELinux details to diagnostics bundle (DCOS_OSS-4123)

* Add external Mesos master/agent logs in the diagnostic bundle (DCOS_OSS-4283)

* Update Java to 8u192. (DCOS_OSS-4380)

* Docker-GC will now log to journald. (COPS-4044)

* Allow the DC/OS installer to be used when there is a space in its path (DCOS_OSS-4429).

* Admin Router logs to non-blocking socket. (DCOS-43956)

* Add path-based routing to AR to routing requests to `dcos-net` (DCOS_OSS-1837)

* Mark `dcos6` overlay network as disabled if `enable_ipv6` is set to false (DCOS-40539)

### Notable changes

* Bumped DC/OS UI to [master+v2.40.10](https://github.com/dcos/dcos-ui/releases/tag/master%2Bv2.40.10)
