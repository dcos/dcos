## DC/OS 1.13.0

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


### Highlights

#### Introduction of service accounts, alignment of authentication architectures

The core of the DC/OS Enterprise identity and access management service (IAM) has been open-sourced and added to DC/OS, replacing `dcos-oauth`. CockroachDB was added as a DC/OS component as a highly available database serving the IAM.

With that DC/OS now supports service accounts. Service accounts allow individual tools and applications to interact with a DC/OS cluster using their own identity. A successful service account login results in authentication proof -- the DC/OS authentication token. A valid DC/OS authentication token is required in order to access DC/OS services and components through Master Admin Router.

This change also aligned the authentication architectures between DC/OS Enterprise and DC/OS: the HTTP API for service account management as well as for service account login is now the same in both systems. The DC/OS authentication token implementation details are equivalent in both systems: it is a JSON Web Token (JWT) of type RS256 which can be validated by any component in the system after consulting the IAM's JSON Web Key Set (JWKS) endpoint.


### What's new

* Admin Router Nginx Virtual Hosts metrics are now collected by default. An Nginx instance metrics display is available on `/nginx/status` on each DC/OS master node. (DCOS_OSS-4562)

* CockroachDB metrics are now collected by Telegraf (DCOS_OSS-4529).

* ZooKeeper metrics are now collected by Telegraf (DCOS_OSS-4477).

* Mesos metrics are now available by default. (DCOS_OSS-3815)

* Metronome supports UCR

* Metronome supports file based secrets

* Metronome supports hybrid cloud

* Marathon metrics are now collected by Telegraf (DCOS-47693)

* Expose Public IP (DCOS_OSS-4514)

* Add thisnode.thisdcos.directory dns zone (DCOS_OSS-4666)

* Make cluster identity configurable in dcos-net (DCOS_OSS-4620)

* Prometheus-format metrics can be gathered from tasks (DCOS_OSS-3717)

* Expose a Mesos flag to allow the network CNI root directory to be persisted across host reboot (DCOS_OSS-4667)

* Expose internal metrics for the Telegraf metrics pipeline (DCOS_OSS-4608)

* Allow setting environment variables for `docker-gc` in `/var/lib/dcos/docker-gc.env`

* CockroachDB has been updated to version 2.0.7


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

* Fix CLI task metrics summary command which was occasionally failing to find metrics (DCOS_OSS-4679)

* Improve error message in case Docker is not running at start of installation (DCOS-15890)

* Stop requiring `ssh_user` attribute in `config.yaml` when using parts of deprecated CLI installer (DCOS_OSS-4613)

### Notable changes

* Bumped DC/OS UI to [master+v2.40.10](https://github.com/dcos/dcos-ui/releases/tag/master%2Bv2.40.10)
