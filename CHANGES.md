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

* Release of Marathon 1.8 with refactored Task Instance management.

* Telegraf's statsd input plugin reports additional internal metrics. (DCOS_OSS-4759)

* Telegraf's procstat input plugin reports process metrics (DCOS-50778).

* Admin Router Nginx Virtual Hosts metrics are now collected by default. An Nginx instance metrics display is available on `/nginx/status` on each DC/OS master node. (DCOS_OSS-4562)

* CockroachDB metrics are now collected by Telegraf (DCOS_OSS-4529).

* ZooKeeper metrics are now collected by Telegraf (DCOS_OSS-4477).

* Exhibitor metrics are now collected by Telegraf (DCOS-45353).

* Marathon and Metronome have DC/OS install flag to configure GPU support.  "restricted", "unrestricted", "undefined" and "" are valid.

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

* Admin Router returns relative redirects to avoid relying on the Host header (DCOS-47845)

* Introduced the `dcos-ui-update-service`, this component exposes an API to update the servered `dcos-ui` version using the `dcos-ui` package published to Universe.

* Add basic support for prometheus to dcos-net (DCOS_OSS-4738)

* Add Metrics for dns forwarding (DCOS-48336)

* Add metrics for lashup (DCOS_OSS-4756)

* DC/OS UI X-Frame-Options value can be configured (DCOS-49594)


### Breaking changes


### Known limitations

* Authentication tokens emitted by `dcos-oauth` prior to an upgrade from DC/OS version 1.12.x to DC/OS version 1.13.x will become invalid during the upgrade. Simply log in again.


### Fixed and improved

* Prefix illegal prometheus metric names with an underscore (DCOS_OSS-4899)

* Fix dcos-net-setup.py failing when systemd network directory did not exist (DCOS-49711)
* Updated REX-Ray version to 0.11.4 (DCOS_OSS-4316) (COPS-3961) [rexray v0.11.4](https://github.com/rexray/rexray/releases/tag/v0.11.4)

* Telegraf is upgraded to 1.9.4. (DCOS_OSS-4675)

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

* Add a warning to the installer to let the user know if case kernel modules required by DSS are not loaded (DCOS-49088)

* Enable ipv6 support for l4lb by default (DCOS_OSS-1993)

* Upgrade OTP version to 21.3 (DCOS_OSS-4902)

* Fix a race condition in L4LB (DCOS_OSS-4939)

* Fix IPv6 VIP support in L4LB (DCOS-50427)

### Notable changes

* Bumped DC/OS UI to [master+v2.40.10](https://github.com/dcos/dcos-ui/releases/tag/master%2Bv2.40.10)
